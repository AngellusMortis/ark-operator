"""ARK operator code for PVCs."""

import json
import logging
from typing import Literal

import kopf
import yaml

from ark_operator.ark.utils import ARK_SERVER_IMAGE_VERSION
from ark_operator.data import ArkClusterSpec
from ark_operator.k8s import (
    get_v1_batch_client,
)
from ark_operator.templates import loader

JOB_RETRIES = 3

ERROR_CHECK_UPDATE_JOB = "Failed to create check update cron job."
_LOGGER = logging.getLogger(__name__)


async def update_check_update_cron_job(  # noqa: PLR0913
    *,
    name: str,
    namespace: str,
    active_volume: Literal["server-a", "server-b"],
    spec: ArkClusterSpec,
    logger: kopf.Logger | None = None,
    do_update: bool = False,
    dry_run: bool = False,
) -> None:
    """Create cronjob to check for updates."""

    logger = logger or _LOGGER
    job_tmpl = loader.get_template("check-update-cronjob.yml.j2")
    job = yaml.safe_load(
        await job_tmpl.render_async(
            instance_name=name,
            namespace=namespace,
            active_volume=active_volume,
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
        )
    )

    v1 = await get_v1_batch_client()
    try:
        if do_update:
            obj = await v1.patch_namespaced_cron_job(
                name=f"{name}-check-update", namespace=namespace, body=job
            )
        else:
            obj = await v1.create_namespaced_cron_job(
                namespace=namespace,
                body=job,
            )
    except Exception as ex:
        raise kopf.PermanentError(ERROR_CHECK_UPDATE_JOB) from ex

    logger.info("Created Check update cron job: %s", obj.metadata.name)


async def delete_check_update_cron_job(
    *, name: str, namespace: str, logger: kopf.Logger | None = None
) -> None:
    """Check cronjob to check for updates."""

    logger = logger or _LOGGER
    v1 = await get_v1_batch_client()
    try:
        await v1.delete_namespaced_cron_job(
            name=f"{name}-check-update", namespace=namespace
        )
    except Exception as ex:  # noqa: BLE001
        logger.warning("Failed to delete check update cron job: %s", name, exc_info=ex)
