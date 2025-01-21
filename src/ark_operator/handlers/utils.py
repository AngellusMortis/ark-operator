"""Utils for kopf."""

from environs import Env

ENV = Env()
DRY_RUN = ENV.bool("ARK_OP_KOPF_DRY_RUN", ENV.bool("ARK_OP_DRY_RUN", False))
DEFAULT_NAME = "ark"
DEFAULT_NAMESPACE = "default"

ERROR_WAIT_PVC = "Waiting for PVC to complete"
ERROR_WAIT_INIT_JOB = "Waiting for volume init job to complete."
ERROR_WAIT_INIT_RESOURCES = "Waiting for resources to be created."
ERROR_WAIT_UPDATE_JOB = "Waiting for server update job to complete."

TRACKED_INSTANCES: set[tuple[str, str]] = set()


def add_tracked_instance(name: str | None, namespace: str | None) -> None:
    """Add tracked instance."""

    TRACKED_INSTANCES.add((name or DEFAULT_NAME, namespace or DEFAULT_NAMESPACE))


def remove_tracked_instance(name: str | None, namespace: str | None) -> None:
    """Remove tracked instance."""

    TRACKED_INSTANCES.remove((name or DEFAULT_NAME, namespace or DEFAULT_NAMESPACE))


def is_tracked(name: str | None, namespace: str | None) -> bool:
    """Check if instance is tracked."""

    return (name or DEFAULT_NAME, namespace or DEFAULT_NAMESPACE) in TRACKED_INSTANCES
