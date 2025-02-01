"""Misc handlers for kopf."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from pathlib import Path
from tempfile import gettempdir
from typing import TYPE_CHECKING, Literal, Unpack

import kopf

from ark_operator.ark import (
    check_update_job,
    close_cf_client,
    create_server_pod,
    create_update_job,
    get_active_buildid,
    get_active_volume,
    get_mod_status,
    get_mod_updates,
    get_server_pod,
    has_cf_auth,
    is_server_pod_ready,
)
from ark_operator.data import (
    ActivityEvent,
    ArkClusterSpec,
    ArkClusterStatus,
    TimerEvent,
)
from ark_operator.handlers.utils import (
    DEFAULT_NAME,
    DEFAULT_NAMESPACE,
    DRY_RUN,
    ENV,
    ERROR_WAIT_UPDATE_JOB,
    add_tracked_instance,
    create_restart_lock,
    restart_with_lock,
)
from ark_operator.k8s import get_k8s_client
from ark_operator.log import DEFAULT_LOG_CONFIG, init_logging
from ark_operator.rcon import close_clients
from ark_operator.steam import Steam
from ark_operator.utils import utc_now

if TYPE_CHECKING:
    from kopf import Patch

ARK_UPDATE_INTERVAL = timedelta(minutes=15).total_seconds()
ARK_LAST_UPDATE_CHECK = timedelta(minutes=30)


@kopf.on.startup()  # type: ignore[arg-type]
async def startup(**kwargs: Unpack[ActivityEvent]) -> None:
    """Kopf startup handler."""

    level = ENV("ARK_OP_LOG_LEVEL", "INFO")
    settings = kwargs["settings"]
    logger = kwargs["logger"]

    settings.posting.level = logging.getLevelNamesMapping()[level]
    init_logging(
        ENV("ARK_OP_LOG_FORMAT", "auto"),
        level,
        config=ENV.dict("ARK_OP_LOG_CONFIG", None) or DEFAULT_LOG_CONFIG,
    )
    create_restart_lock()
    await get_k8s_client()
    if not has_cf_auth():
        logger.warning("No CurseForge API key provided, will not do mod update checks")


@kopf.on.cleanup()  # type: ignore[arg-type]
async def cleanup(**kwargs: Unpack[ActivityEvent]) -> None:
    """Kopf cleanup handler."""

    logger = kwargs["logger"]
    client = await get_k8s_client()
    try:
        await client.close()
    except Exception as ex:  # noqa: BLE001
        logger.warning("Failed to close k8s client", exc_info=ex)
    try:
        await close_clients()
    except Exception as ex:  # noqa: BLE001
        logger.warning("Failed to close RCON client(s)", exc_info=ex)

    await close_cf_client()


async def _update_server(  # noqa: PLR0913
    *,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
    logger: kopf.Logger,
    status: ArkClusterStatus,
    patch: Patch,
) -> None:
    status.state = "Updating Server"
    status.ready = False
    patch.status.update(**status.model_dump(include={"state", "ready"}))
    logger.debug("status update %s", patch.status)
    active_volume = status.active_volume or await get_active_volume(
        name=name, namespace=namespace, spec=spec
    )
    update_volume: Literal["server-a", "server-b"] = (
        "server-a" if active_volume == "server-b" else "server-b"
    )

    try:
        job_result = await check_update_job(
            name=name, namespace=namespace, logger=logger
        )
        if not job_result:
            logger.info("Update job does not exist yet, creating it")
            active_volume = status.active_volume or await get_active_volume(
                name=name, namespace=namespace, spec=spec
            )
            await create_update_job(
                name=name,
                namespace=namespace,
                spec=spec,
                logger=logger,
                dry_run=DRY_RUN,
                active_volume=active_volume,
            )
            raise kopf.TemporaryError(ERROR_WAIT_UPDATE_JOB, delay=30)
    except kopf.PermanentError as ex:
        patch.status["state"] = f"Error: {ex!s}"
        logger.debug("status update %s", patch.status)
        raise

    await check_update_job(
        name=name, namespace=namespace, logger=logger, force_delete=True
    )

    active_volume = status.active_volume or await get_active_volume(
        name=name, namespace=namespace, spec=spec
    )
    await restart_with_lock(
        name=name,
        namespace=namespace,
        spec=spec,
        active_volume=active_volume,
        active_buildid=status.active_buildid,
        reason="ARK update",
        logger=logger,
        dry_run=DRY_RUN,
    )

    status.ready = True
    status.state = "Running"
    status.active_buildid = status.latest_buildid
    status.active_volume = update_volume
    patch.status.update(
        **status.model_dump(
            include={"state", "ready", "active_buildid", "active_volume"}
        )
    )
    logger.debug("status update %s", patch.status)


@kopf.timer(  # type: ignore[arg-type]
    "arkcluster", interval=ARK_UPDATE_INTERVAL, initial_delay=60
)
async def check_updates(**kwargs: Unpack[TimerEvent]) -> None:
    """Check for ARK server updates."""

    status = ArkClusterStatus(**kwargs["status"])
    spec = ArkClusterSpec(**kwargs["spec"])
    patch = kwargs["patch"]
    logger = kwargs["logger"]
    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs["namespace"] or DEFAULT_NAMESPACE

    if not status.ready or not status.state or not status.state.startswith("Running"):
        logger.info("Skipping update check because cluster is not ready.")
        return

    if DRY_RUN:
        latest_version = 1
    else:
        steam = Steam(Path(gettempdir()) / "steam")
        latest_version = await steam.get_latest_ark_buildid()
    status.latest_buildid = latest_version
    patch.status.update(**status.model_dump(include={"latest_buildid"}))
    logger.debug("status update %s", patch.status)
    logger.info("Latest ARK version: %s", latest_version)

    active_version = status.active_buildid or 1
    # ARK update needs to happen first
    if latest_version > active_version:
        logger.info("ARK needs update %s -> %s", active_version, latest_version)
        return

    if not has_cf_auth():
        logger.info("Skipping mod update check because no CurseForge API key")
        return

    mods = await get_mod_status(name=name, namespace=namespace, spec=spec)
    if not mods:
        return
    mod_updates = get_mod_updates(status, mods)

    if not mod_updates:
        logger.info("No mods with updates")
        status.mods = {f"id_{m.id}": m.file_id for m in mods.values()}
        patch.status.update(mods=status.mods)
        return

    logger.info("Mods have updates: %s", mod_updates)
    maps_to_update = set()
    for mod in mod_updates.values():
        maps_to_update |= mod.maps
    if len(mod_updates) > 2:  # noqa: PLR2004
        reason = "multiple mod updates"
    else:
        reason = f"mod update ({', '.join(m.name for m in mod_updates.values())})"
    reason = reason.replace("'", "")

    active_volume = status.active_volume or await get_active_volume(
        name=name, namespace=namespace, spec=spec
    )
    await restart_with_lock(
        name=name,
        namespace=namespace,
        spec=spec,
        reason=reason,
        active_volume=active_volume,
        active_buildid=status.active_buildid,
        servers=list(maps_to_update),
        logger=logger,
        mod_status={f"id_{m.id}": m.file_id for m in mods.values()},
    )


async def _check_initial_status(  # noqa: PLR0913
    *,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
    status: ArkClusterStatus,
    patch: kopf.Patch,
    logger: kopf.Logger,
) -> None:
    if not status.ready and (
        status.state.startswith("Running") or status.state is None
    ):
        status.ready = True
        if status.state is None:
            status.state = "Running"
        patch.status.update(**status.model_dump(include={"state", "ready"}))
        logger.debug("status update %s", patch.status)

    if status.ready and status.active_volume is None:
        status.active_volume = await get_active_volume(
            name=name, namespace=namespace, spec=spec
        )
        patch.status.update(**status.model_dump(include={"active_volume"}))
        logger.debug("status update %s", patch.status)
    if status.ready and status.active_buildid is None:
        status.active_buildid = (
            await get_active_buildid(name=name, namespace=namespace, spec=spec)
            or status.latest_buildid
        )
        patch.status.update(**status.model_dump(include={"active_buildid"}))
        logger.debug("status update %s", patch.status)


def _is_ready(
    *,
    spec: ArkClusterSpec,
    status: ArkClusterStatus,
    patch: kopf.Patch,
    logger: kopf.Logger,
) -> bool:
    if not status.ready and status.state == "Updating Server":
        return True

    now = utc_now()
    if (
        not status.ready
        and status.last_update
        and (now - status.last_update) > ARK_LAST_UPDATE_CHECK
    ):
        logger.warning("No status recent status update for cluster, force reseting")
        status.ready = True
        status.state = "Running"
        patch.status.update(
            **status.model_dump(
                include={
                    "ready",
                    "state",
                }
            )
        )
        return True

    if not status.ready or not status.state or not status.state.startswith("Running"):
        status.created_pods = 0
        status.ready_pods = 0
        status.total_pods = len(spec.server.active_maps)
        status.suspended_pods = len(spec.server.suspend)
        patch.status.update(
            **status.model_dump(
                include={
                    "ready",
                    "created_pods",
                    "ready_pods",
                    "total_pods",
                    "state",
                    "suspended_pods",
                }
            )
        )
        logger.debug("status update %s", patch.status)

        logger.info("Skipping status check because cluster is not ready.")
        return False
    return True


async def _create_pods(
    *,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
    status: ArkClusterStatus,
    logger: kopf.Logger,
) -> bool:
    active_volume = status.active_volume or await get_active_volume(
        name=name, namespace=namespace, spec=spec
    )
    logger.info(
        "Creating missing server pods: %s (%s)",
        spec.server.active_maps,
        spec.server.suspend,
    )
    try:
        created = await asyncio.gather(
            *[
                create_server_pod(
                    name=name,
                    namespace=namespace,
                    map_id=m,
                    active_volume=active_volume,
                    active_buildid=status.active_buildid,
                    spec=spec,
                    logger=logger,
                    dry_run=DRY_RUN,
                )
                for m in spec.server.active_maps
            ]
        )
    except Exception as ex:  # noqa: BLE001
        logger.warning("Failed to create server pods", exc_info=ex)
        return True

    if any(created):
        logger.info("Created %s server pod(s)", len([x for x in created if x]))
        return True
    return False


@kopf.timer(  # type: ignore[arg-type]
    "arkcluster", interval=15, initial_delay=30
)
async def check_status(**kwargs: Unpack[TimerEvent]) -> None:
    """Check for ARK server updates."""

    status = ArkClusterStatus(**kwargs["status"])
    spec = ArkClusterSpec(**kwargs["spec"])
    patch = kwargs["patch"]
    logger = kwargs["logger"]
    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE

    add_tracked_instance(name=name, namespace=namespace)
    await _check_initial_status(
        name=name,
        namespace=namespace,
        spec=spec,
        status=status,
        patch=patch,
        logger=logger,
    )
    if not _is_ready(spec=spec, status=status, patch=patch, logger=logger):
        return

    if await _create_pods(
        name=name, namespace=namespace, spec=spec, status=status, logger=logger
    ):
        return

    if (
        status.latest_buildid
        and status.active_buildid
        and status.latest_buildid > status.active_buildid
    ):
        logger.info(
            "Updating cluster from %s to %s",
            status.latest_buildid,
            status.active_buildid,
        )
        await _update_server(
            name=name,
            namespace=namespace,
            spec=spec,
            logger=logger,
            status=status,
            patch=patch,
        )
        return

    await check_update_job(
        name=name, namespace=namespace, logger=logger, force_delete=True
    )

    containers = 0
    ready = 0
    total = len(spec.server.active_maps)
    for map_id in spec.server.active_maps:
        try:
            obj = await get_server_pod(name=name, namespace=namespace, map_id=map_id)
        except Exception as ex:  # noqa: BLE001
            logger.warning("Failed to get server pod", exc_info=ex)
            return

        if not obj:
            continue

        containers += 1
        if is_server_pod_ready(obj):
            ready += 1

    logger.info(
        "Status: ready: %s, running: %s, total: %s, suspeded: %s",
        ready,
        containers,
        total,
        len(spec.server.suspend),
    )
    status.ready = True
    status.created_pods = containers
    status.ready_pods = ready
    status.total_pods = total
    status.state = f"Running ({ready}/{containers}/{total})"
    status.suspended_pods = len(spec.server.suspend)

    patch.status.update(
        **status.model_dump(
            include={
                "ready",
                "created_pods",
                "ready_pods",
                "total_pods",
                "state",
                "suspended_pods",
            }
        )
    )
    logger.debug("status update %s", patch.status)
