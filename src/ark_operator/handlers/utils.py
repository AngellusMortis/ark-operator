"""Utils for kopf."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING

from environs import Env

from ark_operator.ark import get_server_pod, restart_server_pods

if TYPE_CHECKING:
    from datetime import datetime

    import kopf

    from ark_operator.data import ArkClusterSpec

ENV = Env()
DRY_RUN = ENV.bool("ARK_OP_KOPF_DRY_RUN", ENV.bool("ARK_OP_DRY_RUN", False))
DEFAULT_NAME = "ark"
DEFAULT_NAMESPACE = "default"

ERROR_WAIT_PVC = "Waiting for PVC to complete"
ERROR_WAIT_INIT_JOB = "Waiting for volume init job to complete."
ERROR_UPDATE_STATUS = "Waiting for status update."
ERROR_WAIT_INIT_RESOURCES = "Waiting for resources to be created."
ERROR_WAIT_UPDATE_JOB = "Waiting for server update job to complete."
ERROR_NO_LOCK = "Restart lock has not been created yet."
ERROR_RESTARTING = "Waiting for restart to complete."

TRACKED_INSTANCES: set[tuple[str, str]] = set()
RESTART_LOCK: asyncio.Lock | None = None


def add_tracked_instance(name: str | None, namespace: str | None) -> None:
    """Add tracked instance."""

    TRACKED_INSTANCES.add((name or DEFAULT_NAME, namespace or DEFAULT_NAMESPACE))


def remove_tracked_instance(name: str | None, namespace: str | None) -> None:
    """Remove tracked instance."""

    with suppress(KeyError):
        TRACKED_INSTANCES.remove((name or DEFAULT_NAME, namespace or DEFAULT_NAMESPACE))


def is_tracked(name: str | None, namespace: str | None) -> bool:
    """Check if instance is tracked."""

    return (name or DEFAULT_NAME, namespace or DEFAULT_NAMESPACE) in TRACKED_INSTANCES


def create_restart_lock() -> None:
    """Create restart lock for cluster."""

    global RESTART_LOCK  # noqa: PLW0603

    RESTART_LOCK = asyncio.Lock()


def get_restart_lock() -> asyncio.Lock:
    """Get restart lock."""

    if not RESTART_LOCK:
        raise RuntimeError(ERROR_NO_LOCK)

    return RESTART_LOCK


async def _check_servers_start(
    *, name: str, namespace: str, servers: list[str], trigger_time: datetime
) -> list[str]:
    to_restart = []
    for map_id in servers:
        pod = await get_server_pod(name=name, namespace=namespace, map_id=map_id)
        if not pod:
            continue
        if pod.metadata.creation_timestamp < trigger_time:
            to_restart.append(map_id)

    return to_restart


async def restart_with_lock(  # noqa: PLR0913
    *,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
    reason: str,
    active_volume: str,
    active_buildid: int | None,
    logger: kopf.Logger,
    trigger_time: datetime | None = None,
    servers: list[str] | None = None,
    mod_status: dict[str, int] | None = None,
    dry_run: bool = False,
) -> None:
    """Do restart with lock."""

    lock = get_restart_lock()
    if lock.locked():
        logger.info("Restart already in progress, waiting until it completes")
        return

    await lock.acquire()
    try:
        if trigger_time:
            servers = await _check_servers_start(
                name=name,
                namespace=namespace,
                servers=servers or spec.server.active_maps,
                trigger_time=trigger_time,
            )
            if not servers:
                logger.info(
                    "Skipping restart because all servers have already been restarted."
                )
                return

        await restart_server_pods(
            name=name,
            namespace=namespace,
            spec=spec,
            reason=reason,
            active_volume=active_volume,
            active_buildid=active_buildid,
            servers=servers,
            logger=logger,
            mod_status=mod_status,
            dry_run=dry_run,
        )
    finally:
        lock.release()
