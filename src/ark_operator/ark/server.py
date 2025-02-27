"""ARK operator code for PVCs."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from datetime import timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Literal, cast

import httpx
import kopf
import yaml
from kubernetes_asyncio.client import ApiException

from ark_operator.ark.conf import get_map_envs, get_rcon_password, get_secrets
from ark_operator.ark.service import get_cluster_host
from ark_operator.ark.utils import (
    ARK_SERVER_IMAGE_VERSION,
    get_map_name,
    get_map_slug,
    order_maps,
)
from ark_operator.k8s import get_v1_client, update_cluster
from ark_operator.rcon import close_client, close_clients, send_cmd_all
from ark_operator.templates import loader
from ark_operator.utils import VERSION, human_format, notify_intervals, utc_now

if TYPE_CHECKING:
    from kubernetes_asyncio.client import V1Pod

    from ark_operator.data import ArkClusterSpec

ERROR_POD = "Error creating server pod for map {map_id}"
_LOGGER = logging.getLogger(__name__)


async def get_server_pod(*, name: str, namespace: str, map_id: str) -> V1Pod | None:
    """Get server pod."""

    map_slug = get_map_slug(map_id)
    pod_name = f"{name}-{map_slug}"

    v1 = await get_v1_client()
    try:
        obj = await v1.read_namespaced_pod(namespace=namespace, name=pod_name)
    except ApiException as ex:
        if ex.status == HTTPStatus.NOT_FOUND:
            return None
        raise  # TODO: # pragma: no cover

    return obj


async def get_active_version(
    name: str, namespace: str, spec: ArkClusterSpec
) -> str | None:
    """Get active container version."""

    for map_id in spec.server.all_maps:
        pod = await get_server_pod(name=name, namespace=namespace, map_id=map_id)
        if pod:
            break

    if not pod:
        return None

    for container in pod.spec.containers:
        if container.name != "ark":
            continue

        image = cast(str, container.image)
        return image.split(":")[-1]
    return None


async def get_active_volume(
    name: str, namespace: str, spec: ArkClusterSpec
) -> Literal["server-a", "server-b"]:
    """Get active_volume."""

    for map_id in spec.server.all_maps:
        pod = await get_server_pod(name=name, namespace=namespace, map_id=map_id)
        if pod:
            break

    if not pod:
        return "server-a"

    return cast(
        Literal["server-a", "server-b"],
        pod.metadata.labels["mort.is/active-volume"],
    )


async def get_active_buildid(
    name: str, namespace: str, spec: ArkClusterSpec
) -> int | None:
    """Get active_buildid."""

    for map_id in spec.server.all_maps:
        pod = await get_server_pod(name=name, namespace=namespace, map_id=map_id)
        if pod:
            break

    if not pod:
        return None

    if "mort.is/ark-build" in pod.metadata.labels:
        return int(pod.metadata.labels["mort.is/ark-build"])
    return None


def is_server_pod_ready(pod: V1Pod | None) -> bool:
    """Check if server pod is ready."""

    if not pod or not pod.status or not pod.status.container_statuses:
        return False

    container_ready = [s.ready for s in pod.status.container_statuses]
    return all(container_ready)


async def _patch_server_pod(
    *, pod_name: str, namespace: str, body: dict[str, Any]
) -> V1Pod:
    v1 = await get_v1_client()
    try:
        obj = await v1.patch_namespaced_pod(
            name=pod_name,
            namespace=namespace,
            body=body,
        )
    except ApiException as ex:
        if ex.status == HTTPStatus.UNPROCESSABLE_ENTITY:
            await v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
            obj = await v1.patch_namespaced_pod(
                name=pod_name,
                namespace=namespace,
                body=body,
            )
        else:
            raise

    return obj


async def create_server_pod(  # noqa: PLR0913
    *,
    name: str,
    namespace: str,
    map_id: str,
    active_volume: str,
    spec: ArkClusterSpec,
    logger: kopf.Logger | None = None,
    dry_run: bool = False,
    active_buildid: int | None = None,
    force_create: bool = False,
) -> bool:
    """Create ARK server job."""

    logger = logger or _LOGGER
    exists = (
        await get_server_pod(name=name, namespace=namespace, map_id=map_id) is not None
    )

    if exists and not force_create:
        return False

    v1 = await get_v1_client()
    map_name = get_map_name(map_id)
    map_slug = get_map_slug(map_id)
    pod_name = f"{name}-{map_slug}"
    envs = await get_map_envs(name=name, namespace=namespace, spec=spec, map_id=map_id)
    has_global_gus = "ARK_SERVER_GLOBAL_GUS" in envs
    has_global_game = "ARK_SERVER_GLOBAL_GAME" in envs
    has_map_gus = "ARK_SERVER_MAP_GUS" in envs
    has_map_game = "ARK_SERVER_MAP_GAME" in envs

    pod_tmpl = loader.get_template("server-pod.yml.j2")
    pod = yaml.safe_load(
        await pod_tmpl.render_async(
            instance_name=name,
            namespace=namespace,
            uid=spec.run_as_user,
            gid=spec.run_as_group,
            node_selector=json.dumps(spec.node_selector)
            if spec.node_selector
            else None,
            tolerations=json.dumps(spec.tolerations) if spec.tolerations else None,
            resources=json.dumps(spec.server.resources)
            if spec.server.resources
            else None,
            dry_run=dry_run,
            image_version=ARK_SERVER_IMAGE_VERSION,
            operator_version=VERSION,
            map_id=map_id,
            map_name=map_name,
            map_slug=map_slug,
            active_volume=active_volume,
            envs=envs,
            has_global_gus=has_global_gus,
            has_global_game=has_global_game,
            has_map_gus=has_map_gus,
            has_map_game=has_map_game,
            game_port=envs["ARK_SERVER_GAME_PORT"],
            rcon_port=envs["ARK_SERVER_RCON_PORT"],
            active_buildid=active_buildid,
        )
    )

    try:
        if exists:
            obj = await _patch_server_pod(
                pod_name=pod_name,
                namespace=namespace,
                body=pod,
            )
        else:
            obj = await v1.create_namespaced_pod(
                namespace=namespace,
                body=pod,
            )
    except Exception as ex:  # TODO: # pragma: no cover
        # kopf does not log stracktrace
        logger.exception(ERROR_POD.format(map_id=map_id))
        raise kopf.TemporaryError(ERROR_POD.format(map_id=map_id), delay=5) from ex

    logger.info(
        "%s server pod: %s", "Patched" if exists else "Created", obj.metadata.name
    )
    await update_cluster(
        name=name,
        namespace=namespace,
        status={"lastAppliedVersion": ARK_SERVER_IMAGE_VERSION},
    )
    return True


async def delete_server_pod(
    *, name: str, namespace: str, map_id: str, logger: kopf.Logger | None = None
) -> None:
    """Delete secrets for ARK cluster."""

    map_slug = get_map_slug(map_id)
    pod_name = f"{name}-{map_slug}"
    logger = logger or _LOGGER
    logger.info("Deleting server pod %s", pod_name)
    v1 = await get_v1_client()
    try:
        await v1.delete_namespaced_pod(
            name=pod_name, namespace=namespace, propagation_policy="Foreground"
        )
    except Exception:  # noqa: BLE001  # TODO: # pragma: no cover
        logger.warning("Failed to delete server pod %s", pod_name)


async def _send_message(  # noqa: PLR0913
    msg: str,
    *,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
    host: str,
    password: str,
    servers: list[str],
    logger: kopf.Logger | logging.Logger,
) -> None:
    secrets = await get_secrets(name=name, namespace=namespace)
    if secrets.discord_webhook:
        logger.info("Sending message to Discord Webhook: %s", msg)
        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(secrets.discord_webhook, json={"content": msg})
                r.raise_for_status()
            except Exception:
                logger.exception("Error sending Discord Webhook message")

    try:
        await send_cmd_all(
            f"ServerChat {msg}",
            spec=spec.server,
            host=host,
            password=password,
            close=False,
            servers=servers.copy(),
            logger=logger,
        )
    except Exception:  # noqa: BLE001
        logger.warning("Could not send message to servers")


async def _notify_server_pods(  # noqa: PLR0913
    *,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
    reason: str,
    logger: kopf.Logger | logging.Logger,
    servers: list[str],
    host: str,
    password: str,
    wait_interval: timedelta,
    rolling: bool = False,
) -> None:
    if wait_interval.total_seconds() <= 0:
        logger.info("Skipping notify because gracefulShutdown is set to 0")
        return

    with suppress(Exception):
        await close_clients()

    logger.info("Notifying servers of shutdown (rolling: %s)", rolling)
    previous_interval: float | None = None
    for interval in notify_intervals(wait_interval):
        msg = "Rolling Restart" if rolling else "Shutting Down"
        await update_cluster(
            name=name,
            namespace=namespace,
            status={"ready": False, "state": msg},
        )
        if previous_interval:
            wait_seconds = previous_interval - interval
            human_wait = human_format(wait_seconds)
            logger.info("Waiting %s until next interval", human_wait)
            await asyncio.sleep(wait_seconds)

        human_interval = human_format(interval)
        if rolling:
            msg = spec.server.restart_message_format.format(
                interval=human_interval, reason=reason
            )
        else:
            msg = spec.server.shutdown_message_format.format(
                interval=human_interval, reason=reason
            )
        await _send_message(
            msg,
            name=name,
            namespace=namespace,
            spec=spec,
            host=host,
            password=password,
            servers=servers,
            logger=logger,
        )
        previous_interval = interval

    logger.info("Waiting %s until shutdown", human_interval)
    await asyncio.sleep(interval)


async def _close_clients(
    *, spec: ArkClusterSpec, servers: list[str], host: str
) -> None:
    tasks = []
    for map_id in servers:
        server = spec.server.all_servers[map_id]
        tasks.append(close_client(host=host, port=server.rcon_port))

    await asyncio.gather(*tasks)


async def _get_online_servers(
    *,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
    servers: list[str] | None = None,
    logger: kopf.Logger | logging.Logger,
) -> list[str]:
    pods = {
        m: await get_server_pod(name=name, namespace=namespace, map_id=m)
        for m in spec.server.active_maps
    }

    online_servers = [m for m in spec.server.active_maps if pods.get(m)]
    if servers:
        online_servers = list(set(servers).intersection(set(online_servers)))

    for server in list(online_servers):
        if (pod := pods.get(server)) and not is_server_pod_ready(pod):
            logger.info("Deleting offline server pod: %s", server)
            await delete_server_pod(name=name, namespace=namespace, map_id=server)
            online_servers.remove(server)
    return order_maps(online_servers)


async def shutdown_server_pods(  # noqa: PLR0913
    *,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
    reason: str,
    logger: kopf.Logger | None = None,
    host: str | None = None,
    password: str | None = None,
    suspend: bool = False,
    servers: list[str] | None = None,
    wait_interval: timedelta | None = None,
) -> None:
    """Gracefully shutdown ARK Cluster pods for restart."""

    logger = logger or _LOGGER
    password = password or await get_rcon_password(name=name, namespace=namespace)
    host = host or await get_cluster_host(name=name, namespace=namespace, spec=spec)
    if not host:
        logger.error("Skipping shutdown because could not figure out host for cluster")
        return

    wait_interval = (
        wait_interval if wait_interval is not None else spec.server.graceful_shutdown
    )
    online_servers = await _get_online_servers(
        name=name, namespace=namespace, spec=spec, servers=servers, logger=logger
    )
    now = utc_now()
    logger.info("Shutting down servers [suspend: %s] %s", suspend, online_servers)

    await update_cluster(
        name=name,
        namespace=namespace,
        status={
            "ready": False,
            "state": "Shutting Down",
            "restart": {
                "time": (now + wait_interval).isoformat(),
                "type": "shutdown",
                "maps": online_servers,
                "reason": reason,
            },
        },
    )
    try:
        await _notify_server_pods(
            name=name,
            namespace=namespace,
            spec=spec,
            reason=reason,
            logger=logger,
            servers=online_servers,
            host=host,
            password=password,
            rolling=False,
            wait_interval=wait_interval,
        )
    finally:
        await _close_clients(spec=spec, servers=online_servers, host=host)
    if suspend:
        spec.server.suspend |= set(online_servers)
        logger.info("Suspending servers %s", online_servers)
        await update_cluster(
            name=name,
            namespace=namespace,
            spec={"server": {"suspend": spec.server.suspend}},
        )
    await asyncio.gather(
        *[
            delete_server_pod(name=name, namespace=namespace, map_id=m, logger=logger)
            for m in online_servers
        ]
    )
    await update_cluster(
        name=name,
        namespace=namespace,
        status={"ready": True, "state": "Running", "restart": None},
    )


async def restart_server_pods(  # noqa: PLR0913
    *,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
    active_volume: str,
    reason: str,
    logger: kopf.Logger | None = None,
    host: str | None = None,
    password: str | None = None,
    servers: list[str] | None = None,
    active_buildid: int | None = None,
    wait_interval: timedelta | None = None,
    mod_status: dict[str, int] | None = None,
    dry_run: bool = False,
) -> None:
    """Gracefully do rolling restart ARK Cluster pods."""

    logger = logger or _LOGGER
    password = password or await get_rcon_password(name=name, namespace=namespace)
    host = host or await get_cluster_host(name=name, namespace=namespace, spec=spec)
    if not host:
        logger.error("Skipping restart because could not figure out host for cluster")
        return

    wait_interval = (
        wait_interval if wait_interval is not None else spec.server.graceful_shutdown
    )

    online_servers = await _get_online_servers(
        name=name, namespace=namespace, spec=spec, servers=servers, logger=logger
    )
    now = utc_now()
    logger.info("Restarting servers %s", online_servers)
    await update_cluster(
        name=name,
        namespace=namespace,
        status={
            "ready": False,
            "state": "Rolling Restart",
            "restart": {
                "time": (now + wait_interval).isoformat(),
                "type": "restart",
                "maps": online_servers,
                "reason": reason,
                "mods": mod_status,
            },
        },
    )
    await _notify_server_pods(
        name=name,
        namespace=namespace,
        spec=spec,
        reason=reason,
        logger=logger,
        servers=online_servers,
        host=host,
        password=password,
        rolling=True,
        wait_interval=wait_interval,
    )

    await _send_message(
        spec.server.restart_start_message,
        name=name,
        namespace=namespace,
        spec=spec,
        host=host,
        password=password,
        servers=online_servers,
        logger=logger,
    )
    total = len(online_servers)
    servers_to_restart = online_servers.copy()
    for index, map_id in enumerate(online_servers):
        progress = f"({index + 1}/{total})"
        await update_cluster(
            name=name,
            namespace=namespace,
            status={
                "ready": False,
                "state": f"Rolling Restart {progress}",
                "restart": {
                    "time": None,
                    "type": "restart",
                    "maps": servers_to_restart,
                    "reason": reason,
                    "mods": mod_status,
                },
            },
        )
        msg = spec.server.rolling_restart_format.format(
            map_name=get_map_name(map_id), progress=progress
        )
        await _send_message(
            msg,
            name=name,
            namespace=namespace,
            spec=spec,
            host=host,
            password=password,
            servers=online_servers,
            logger=logger,
        )
        await asyncio.sleep(30)

        server = spec.server.all_servers[map_id]
        await close_client(host=host, port=server.rcon_port)
        await delete_server_pod(
            name=name, namespace=namespace, map_id=map_id, logger=logger
        )
        servers_to_restart.remove(map_id)
        await update_cluster(
            name=name,
            namespace=namespace,
            status={
                "ready": False,
                "state": f"Rolling Restart {progress}",
                "restart": {
                    "time": None,
                    "type": "restart",
                    "maps": servers_to_restart,
                    "reason": reason,
                    "mods": mod_status,
                },
            },
        )
        pod = await get_server_pod(name=name, namespace=namespace, map_id=map_id)
        while pod is not None:
            if utc_now() - pod.metadata.creation_timestamp < timedelta(minutes=5):
                break

            logger.info("Waiting for server pod to be deleted %s", map_id)
            await asyncio.sleep(5)
            pod = await get_server_pod(name=name, namespace=namespace, map_id=map_id)

        ready = False
        while not ready:
            if not await get_server_pod(name=name, namespace=namespace, map_id=map_id):
                await create_server_pod(
                    name=name,
                    namespace=namespace,
                    map_id=map_id,
                    spec=spec,
                    logger=logger,
                    active_volume=active_volume,
                    active_buildid=active_buildid,
                    dry_run=dry_run,
                )

            logger.info("Waiting for server pod %s to be ready", map_id)
            await asyncio.sleep(10)
            pod = await get_server_pod(name=name, namespace=namespace, map_id=map_id)
            ready = is_server_pod_ready(pod)
            await update_cluster(
                name=name,
                namespace=namespace,
                status={
                    "ready": False,
                    "state": f"Rolling Restart {progress}",
                    "restart": {
                        "time": None,
                        "type": "restart",
                        "maps": servers_to_restart,
                        "reason": reason,
                        "mods": mod_status,
                    },
                },
            )

    await _send_message(
        spec.server.restart_complete_message,
        name=name,
        namespace=namespace,
        spec=spec,
        host=host,
        password=password,
        servers=online_servers,
        logger=logger,
    )
    status = {"ready": True, "state": "Running", "restart": None}
    if mod_status:
        status["mods"] = mod_status
    await update_cluster(
        name=name,
        namespace=namespace,
        status=status,
    )
