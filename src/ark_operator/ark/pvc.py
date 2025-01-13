"""ARK operator code for PVCs."""

import asyncio
import json
import logging
from http import HTTPStatus

import kopf
import yaml
from environs import Env
from kubernetes_asyncio.client import ApiException

from ark_operator.data import ArkClusterSpec, ArkDataSpec, ArkServerSpec
from ark_operator.k8s import (
    check_pvc_exists,
    create_pvc,
    get_v1_batch_client,
)
from ark_operator.templates import loader

_ENV = Env()
MIN_SIZE_SERVER = _ENV("ARK_OP_MIN_SERVER_SIZE", "50Gi")
JOB_RETRIES = 3

ERROR_PVC_ALREADY_EXISTS = "Failed to create PVC because it already exists."
ERROR_INIT_JOB = "Failed to create volume init job."
ERROR_INIT_JOB_CHECK = "Failed to check on volume init job."
ERROR_WAIT_INIT_POD = "Waiting for volume init pod to completed."
ERROR_INIT_FAILED = "Failed to initialize PVCs."
_LOGGER = logging.getLogger(__name__)


async def update_server_pvc(
    *,
    name: str,
    namespace: str,
    spec: ArkServerSpec,
    logger: kopf.Logger | None = None,
) -> None:
    """Create or update ARK server PVCs."""

    logger = logger or _LOGGER
    tasks = []
    for pvc_name in ["server-a", "server-b"]:
        if not await check_pvc_exists(
            name=f"{name}-{pvc_name}",
            namespace=namespace,
            logger=logger,
            new_size=spec.size,
        ):
            tasks.append(  # noqa: PERF401
                create_pvc(
                    name=pvc_name,
                    instance_name=name,
                    namespace=namespace,
                    storage_class=spec.storage_class,
                    access_mode="ReadWriteMany",
                    size=spec.size,
                    logger=logger,
                    min_size=MIN_SIZE_SERVER,
                )
            )

    if tasks:
        await asyncio.gather(*tasks)


async def update_data_pvc(
    *,
    name: str,
    namespace: str,
    spec: ArkDataSpec,
    logger: kopf.Logger | None = None,
    warn_existing: bool = False,
) -> None:
    """Create or update ARK data PVC."""

    logger = logger or _LOGGER
    full_name = f"{name}-data"
    if not await check_pvc_exists(
        name=full_name, namespace=namespace, logger=logger, new_size=spec.size
    ):
        await create_pvc(
            name="data",
            instance_name=name,
            namespace=namespace,
            storage_class=spec.storage_class,
            access_mode="ReadWriteMany",
            size=spec.size,
            logger=logger,
        )
    elif warn_existing:
        logger.warning("Failed to create PVC because it already exists: %s", name)


async def create_init_job(
    *,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
    logger: kopf.Logger | None = None,
    dry_run: bool = False,
) -> None:
    """Create pod to initialize PVCs."""

    logger = logger or _LOGGER
    job_tmpl = loader.get_template("init-job.yml.j2")
    job = yaml.safe_load(
        await job_tmpl.render_async(
            instance_name=name,
            uid=spec.run_as_user,
            gid=spec.run_as_group,
            node_selector=json.dumps(spec.node_selector)
            if spec.node_selector
            else None,
            tolerations=json.dumps(spec.tolerations) if spec.tolerations else None,
            retries=JOB_RETRIES,
            spec=spec.model_dump_json(),
            dry_run=dry_run,
        )
    )

    v1 = await get_v1_batch_client()
    try:
        obj = await v1.create_namespaced_job(
            namespace=namespace,
            body=job,
        )
    except Exception as ex:
        raise kopf.PermanentError(ERROR_INIT_JOB) from ex

    logger.info("Created Volume init job: %s", obj.metadata.name)


async def check_init_job(
    *,
    name: str,
    namespace: str,
    logger: kopf.Logger | None = None,
    force_delete: bool = False,
) -> bool:
    """Check if PVC init pod has completed and clean it up."""

    logger = logger or _LOGGER
    full_name = f"{name}-init"
    v1 = await get_v1_batch_client()
    logger.debug("Fetching init job")
    try:
        obj = await v1.read_namespaced_job(name=full_name, namespace=namespace)
    except ApiException as ex:
        if ex.status == HTTPStatus.NOT_FOUND:
            return False
        raise kopf.TemporaryError(ERROR_INIT_JOB_CHECK, delay=10) from ex

    if obj.status.failed and obj.status.failed >= JOB_RETRIES:
        raise kopf.PermanentError(ERROR_INIT_FAILED)

    completed = bool(obj.status.completion_time)
    if completed or force_delete:
        logger.info("Deleting job %s", full_name)
        await v1.delete_namespaced_job(
            name=full_name, namespace=namespace, propagation_policy="Foreground"
        )
        return completed

    raise kopf.TemporaryError(ERROR_WAIT_INIT_POD, delay=10)
