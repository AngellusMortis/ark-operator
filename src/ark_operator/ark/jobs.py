"""ARK operator code for PVCs."""

import json
import logging
from http import HTTPStatus
from typing import Any, Literal

import kopf
import yaml
from kubernetes_asyncio.client import ApiException

from ark_operator.ark.utils import ARK_SERVER_IMAGE_VERSION
from ark_operator.data import ArkClusterSpec
from ark_operator.k8s import (
    get_v1_batch_client,
)
from ark_operator.templates import loader
from ark_operator.utils import VERSION

JOB_RETRIES = 3

ERROR_JOB = "Failed to create {job_desc} job."
ERROR_JOB_CHECK = "Failed to check on {job_desc} job."
ERROR_WAIT_POD = "Waiting for {job_desc} pod to completed."
ERROR_JOB_FAILED = "Job {job_desc} failed."
_LOGGER = logging.getLogger(__name__)


async def _create_job(  # noqa: PLR0913
    *,
    template: str,
    job_desc: str,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
    logger: kopf.Logger | None = None,
    dry_run: bool = False,
    **extra_context: Any,  # noqa: ANN401
) -> None:
    """Create ARK server job."""

    logger = logger or _LOGGER
    job_tmpl = loader.get_template(template)
    job = yaml.safe_load(
        await job_tmpl.render_async(
            instance_name=name,
            namespace=namespace,
            uid=spec.run_as_user,
            gid=spec.run_as_group,
            node_selector=json.dumps(spec.node_selector)
            if spec.node_selector
            else None,
            tolerations=json.dumps(spec.tolerations) if spec.tolerations else None,
            retries=JOB_RETRIES,
            spec=spec.model_dump_json(),
            dry_run=dry_run,
            image_version=ARK_SERVER_IMAGE_VERSION,
            operator_version=VERSION,
            **extra_context,
        )
    )

    v1 = await get_v1_batch_client()
    try:
        obj = await v1.create_namespaced_job(
            namespace=namespace,
            body=job,
        )
    except Exception as ex:
        raise kopf.PermanentError(ERROR_JOB.format(job_desc=job_desc)) from ex

    logger.info("Created %s job: %s", job_desc, obj.metadata.name)


async def _check_job(
    *,
    job_name: str,
    job_desc: str,
    namespace: str,
    logger: kopf.Logger | None = None,
    force_delete: bool = False,
) -> bool:
    """Check if job has completed and clean it up."""

    logger = logger or _LOGGER
    v1 = await get_v1_batch_client()
    logger.debug("Fetching init job")
    try:
        obj = await v1.read_namespaced_job(name=job_name, namespace=namespace)
    except ApiException as ex:
        if ex.status == HTTPStatus.NOT_FOUND:
            return False
        raise kopf.TemporaryError(
            ERROR_JOB_CHECK.format(job_desc=job_desc), delay=10
        ) from ex

    if obj.status.failed and obj.status.failed >= JOB_RETRIES:
        raise kopf.PermanentError(ERROR_JOB_FAILED.format(job_desc=job_desc))

    completed = bool(obj.status.completion_time)
    if completed or force_delete:
        logger.info("Deleting job %s", job_name)
        await v1.delete_namespaced_job(
            name=job_name, namespace=namespace, propagation_policy="Foreground"
        )
        return completed

    raise kopf.TemporaryError(ERROR_WAIT_POD.format(job_desc=job_desc), delay=10)


async def create_init_job(
    *,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
    logger: kopf.Logger | None = None,
    dry_run: bool = False,
) -> None:
    """Create job to initialize PVCs."""

    await _create_job(
        template="init-job.yml.j2",
        job_desc="volume init",
        name=name,
        namespace=namespace,
        spec=spec,
        logger=logger,
        dry_run=dry_run,
    )


async def check_init_job(
    *,
    name: str,
    namespace: str,
    logger: kopf.Logger | None = None,
    force_delete: bool = False,
) -> bool:
    """Check if PVC init job has completed and clean it up."""

    return await _check_job(
        job_name=f"{name}-init",
        job_desc="volume init",
        namespace=namespace,
        logger=logger,
        force_delete=force_delete,
    )


async def create_update_job(  # noqa: PLR0913
    *,
    name: str,
    namespace: str,
    active_volume: Literal["server-a", "server-b"],
    spec: ArkClusterSpec,
    logger: kopf.Logger | None = None,
    dry_run: bool = False,
) -> None:
    """Create job to update ARK server volume."""

    update_volume = "server-a" if active_volume == "server-b" else "server-b"

    await _create_job(
        template="update-job.yml.j2",
        job_desc="server update",
        name=name,
        namespace=namespace,
        spec=spec,
        logger=logger,
        dry_run=dry_run,
        update_volume=update_volume,
    )


async def check_update_job(
    *,
    name: str,
    namespace: str,
    logger: kopf.Logger | None = None,
    force_delete: bool = False,
) -> bool:
    """Check if update server job has completed and clean it up."""

    return await _check_job(
        job_name=f"{name}-update",
        job_desc="server update",
        namespace=namespace,
        logger=logger,
        force_delete=force_delete,
    )
