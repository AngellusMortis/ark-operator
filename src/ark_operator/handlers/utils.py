"""Utils for kopf."""

import asyncio

import kopf
from environs import Env

from ark_operator.ark import restart_server_pods
from ark_operator.data import ArkClusterSpec

ENV = Env()
DRY_RUN = ENV.bool("ARK_OP_KOPF_DRY_RUN", ENV.bool("ARK_OP_DRY_RUN", False))
DEFAULT_NAME = "ark"
DEFAULT_NAMESPACE = "default"

ERROR_WAIT_PVC = "Waiting for PVC to complete"
ERROR_WAIT_INIT_JOB = "Waiting for volume init job to complete."
ERROR_WAIT_INIT_RESOURCES = "Waiting for resources to be created."
ERROR_WAIT_UPDATE_JOB = "Waiting for server update job to complete."
ERROR_NO_LOCK = "Restart lock has not been created yet."

TRACKED_INSTANCES: set[tuple[str, str]] = set()
RESTART_LOCK: asyncio.Lock | None = None


def add_tracked_instance(name: str | None, namespace: str | None) -> None:
    """Add tracked instance."""

    TRACKED_INSTANCES.add((name or DEFAULT_NAME, namespace or DEFAULT_NAMESPACE))


def remove_tracked_instance(name: str | None, namespace: str | None) -> None:
    """Remove tracked instance."""

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


async def restart_with_lock(  # noqa: PLR0913
    *,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
    reason: str,
    active_volume: str,
    logger: kopf.Logger,
) -> None:
    """Do restart with lock."""

    lock = get_restart_lock()
    do_restart = True
    if lock.locked():
        logger.info("Restart already in progress, waiting until it completes")
        do_restart = False
        return

    await lock.acquire()
    try:
        if do_restart:
            await restart_server_pods(
                name=name,
                namespace=namespace,
                spec=spec,
                reason=reason,
                active_volume=active_volume,
                logger=logger,
            )
        else:
            logger.warning("Skipped restart because one was already in progress")
    finally:
        lock.release()
