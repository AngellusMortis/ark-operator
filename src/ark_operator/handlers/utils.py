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
