"""ARK operator code for PVCs."""

from __future__ import annotations

import asyncio
import json
import logging
from http import HTTPStatus
from typing import TYPE_CHECKING

import kopf
import yaml
from kubernetes_asyncio.client import ApiException

from ark_operator.ark.conf import get_map_envs, get_rcon_password
from ark_operator.ark.service import get_cluster_host
from ark_operator.ark.utils import (
    ARK_SERVER_IMAGE_VERSION,
    get_map_name,
    get_map_slug,
    order_maps,
)
from ark_operator.k8s import get_v1_client, update_cluster
from ark_operator.rcon import close_client, send_cmd_all
from ark_operator.templates import loader
from ark_operator.utils import VERSION, human_format, notify_intervals

if TYPE_CHECKING:
    from datetime import timedelta

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


def is_server_pod_ready(pod: V1Pod | None) -> bool:
    """Check if server pod is ready."""

    if not pod or not pod.status or not pod.status.container_statuses:
        return False

    container_ready = [s.ready for s in pod.status.container_statuses]
    return all(container_ready)


async def create_server_pod(  # noqa: PLR0913
    *,
    name: str,
    namespace: str,
    map_id: str,
    active_volume: str,
    spec: ArkClusterSpec,
    logger: kopf.Logger | None = None,
    dry_run: bool = False,
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
        )
    )

    try:
        if exists:
            obj = await v1.patch_namespaced_pod(
                name=pod_name,
                namespace=namespace,
                body=pod,
            )
        else:
            obj = await v1.create_namespaced_pod(
                namespace=namespace,
                body=pod,
            )
    except Exception as ex:  # TODO: # pragma: no cover
        raise kopf.TemporaryError(ERROR_POD.format(map_id=map_id), delay=5) from ex

    logger.info(
        "%s server pod: %s", "Patched" if exists else "Created", obj.metadata.name
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


async def _notify_server_pods(  # noqa: PLR0913
    *,
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

    logger.info("Notifying servers of shutdown (rolling: %s)", rolling)
    previous_interval: float | None = None
    for interval in notify_intervals(wait_interval):
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
        await send_cmd_all(
            f"ServerChat {msg}",
            spec=spec.server,
            host=host,
            password=password,
            close=False,
            servers=servers.copy(),
        )
        previous_interval = interval

    _LOGGER.info("Waiting %s until shutdown", human_interval)
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
) -> list[str]:
    online_servers = [
        m
        for m in spec.server.active_maps
        if await get_server_pod(name=name, namespace=namespace, map_id=m)
    ]

    if servers:
        online_servers = list(set(servers).intersection(set(online_servers)))
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

    wait_interval = wait_interval or spec.server.graceful_shutdown

    online_servers = await _get_online_servers(
        name=name, namespace=namespace, spec=spec, servers=servers
    )
    logger.info("Shutting down servers [suspend: %s] %s", suspend, online_servers)
    await update_cluster(
        name=name,
        namespace=namespace,
        status={"ready": False, "state": "Shutting Down"},
    )
    await _notify_server_pods(
        spec=spec,
        reason=reason,
        logger=logger,
        servers=online_servers,
        host=host,
        password=password,
        rolling=False,
        wait_interval=wait_interval,
    )
    await _close_clients(spec=spec, servers=online_servers, host=host)
    if suspend:
        spec.server.suspend |= set(online_servers)
        logger.info("Suspending servers %s", online_servers)
        await update_cluster(name=name, namespace=namespace, spec=spec)
    await asyncio.gather(
        *[
            delete_server_pod(name=name, namespace=namespace, map_id=m, logger=logger)
            for m in online_servers
        ]
    )
    await update_cluster(
        name=name,
        namespace=namespace,
        status={"ready": True, "state": "Running"},
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
    wait_interval: timedelta | None = None,
    dry_run: bool = False,
) -> None:
    """Gracefully do rolling restart ARK Cluster pods."""

    logger = logger or _LOGGER
    password = password or await get_rcon_password(name=name, namespace=namespace)
    host = host or await get_cluster_host(name=name, namespace=namespace, spec=spec)
    if not host:
        logger.error("Skipping restart because could not figure out host for cluster")
        return

    wait_interval = wait_interval or spec.server.graceful_shutdown

    online_servers = await _get_online_servers(
        name=name, namespace=namespace, spec=spec, servers=servers
    )
    logger.info("Restarting servers %s", online_servers)
    await update_cluster(
        name=name,
        namespace=namespace,
        status={"ready": False, "state": "Rolling Restart"},
    )
    await _notify_server_pods(
        spec=spec,
        reason=reason,
        logger=logger,
        servers=online_servers,
        host=host,
        password=password,
        rolling=True,
        wait_interval=wait_interval,
    )

    await send_cmd_all(
        f"ServerChat {spec.server.restart_start_message}",
        spec=spec.server,
        host=host,
        password=password,
        close=False,
        servers=online_servers.copy(),
    )
    total = len(online_servers)
    for index, map_id in enumerate(online_servers.copy()):
        await update_cluster(
            name=name,
            namespace=namespace,
            status={"ready": False, "state": f"Rolling Restart ({index + 1}/{total})"},
        )
        msg = spec.server.rolling_restart_format.format(map_name=get_map_name(map_id))
        if online_servers:
            await send_cmd_all(
                f"ServerChat {msg}",
                spec=spec.server,
                host=host,
                password=password,
                close=False,
                servers=online_servers.copy(),
            )
        await asyncio.sleep(30)
        online_servers.remove(map_id)

        server = spec.server.all_servers[map_id]
        await close_client(host=host, port=server.rcon_port)
        await delete_server_pod(
            name=name, namespace=namespace, map_id=map_id, logger=logger
        )
        pod = await get_server_pod(name=name, namespace=namespace, map_id=map_id)
        while pod is not None:
            logger.info("Waiting for server pod to be deleted %s", map_id)
            await asyncio.sleep(5)
            pod = await get_server_pod(name=name, namespace=namespace, map_id=map_id)

        await create_server_pod(
            name=name,
            namespace=namespace,
            map_id=map_id,
            spec=spec,
            logger=logger,
            active_volume=active_volume,
            dry_run=dry_run,
        )
        ready = False
        while not ready:
            logger.info("Waiting for server pod %s to be ready", map_id)
            await asyncio.sleep(10)
            pod = await get_server_pod(name=name, namespace=namespace, map_id=map_id)
            ready = is_server_pod_ready(pod)

    await update_cluster(
        name=name, namespace=namespace, status={"ready": True, "state": "Running"}
    )
