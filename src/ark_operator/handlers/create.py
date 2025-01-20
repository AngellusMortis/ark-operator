"""Create handlers for kopf."""

import asyncio
from pathlib import Path
from tempfile import gettempdir
from typing import Unpack

import kopf

from ark_operator.ark import (
    check_init_job,
    create_init_job,
    create_secrets,
    create_server_pod,
    update_data_pvc,
    update_server_pvc,
)
from ark_operator.data import (
    ArkClusterSpec,
    ArkClusterStatus,
    ChangeEvent,
    ClusterStage,
)
from ark_operator.handlers.utils import (
    DEFAULT_NAME,
    DEFAULT_NAMESPACE,
    DRY_RUN,
    ERROR_WAIT_INIT_JOB,
    ERROR_WAIT_INIT_RESOURCES,
    ERROR_WAIT_PVC,
)
from ark_operator.steam import Steam


@kopf.on.resume("arkcluster")  # type: ignore[arg-type]
@kopf.on.create("arkcluster")
async def on_create_init(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    status = kwargs["status"]
    patch = kwargs["patch"]

    if not status.get("state"):  # pragma: no branch
        patch.status.update(**ArkClusterStatus(**status).model_dump())


@kopf.on.resume("arkcluster")  # type: ignore[arg-type]
@kopf.on.create("arkcluster")
async def on_create_state(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    patch = kwargs["patch"]
    retry = kwargs["retry"]
    status = ArkClusterStatus(**kwargs["status"])
    if retry == 0:
        patch.status["ready"] = False
        patch.status["stages"] = None
    elif status.ready:
        status.state = "Running"
        patch.status.update(**status.model_dump(include={"state", "ready"}))
        patch.status["stages"] = None
        patch.status["initalized"] = True
        return

    if retry > 0 and status.is_error:
        patch.status["stages"] = None
        raise kopf.PermanentError

    server_done = status.initalized or status.is_stage_completed(
        ClusterStage.SERVER_PVC
    )
    data_done = status.initalized or status.is_stage_completed(ClusterStage.DATA_PVC)
    if not server_done or not data_done:
        status.state = "Creating PVCs"
        patch.status.update(**status.model_dump(include={"state", "ready"}))
        raise kopf.TemporaryError(ERROR_WAIT_PVC, delay=3)

    init_done = status.initalized or status.is_stage_completed(ClusterStage.INIT_PVC)
    if server_done and data_done and not init_done:
        status.state = "Initializing PVCs"
        patch.status.update(**status.model_dump(include={"state", "ready"}))
        raise kopf.TemporaryError(ERROR_WAIT_PVC, delay=30)

    all_initialized = status.initalized or all([server_done, data_done, init_done])
    create_done = status.is_stage_completed(ClusterStage.CREATE)
    if all_initialized and not create_done:
        status.state = "Creating Resources"
        patch.status.update(**status.model_dump(include={"state", "ready"}))
        raise kopf.TemporaryError(ERROR_WAIT_INIT_RESOURCES, delay=3)

    status.ready = True
    status.state = "Running"
    patch.status.update(**status.model_dump(include={"state", "ready"}))
    patch.status["stages"] = None
    patch.status["initalized"] = True


@kopf.on.resume("arkcluster")  # type: ignore[arg-type]
@kopf.on.create("arkcluster")
async def on_create_server_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    patch = kwargs["patch"]
    if status.initalized or status.is_stage_completed(ClusterStage.SERVER_PVC):
        return

    logger = kwargs["logger"]
    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE
    spec = ArkClusterSpec(**kwargs["spec"])

    try:
        await update_server_pvc(
            name=name,
            namespace=namespace,
            spec=spec.server,
            logger=logger,
        )
    except kopf.PermanentError as ex:
        patch.status["state"] = f"Error: {ex!s}"
        raise

    patch.status["stages"] = status.mark_stage_complete(ClusterStage.SERVER_PVC)


@kopf.on.resume("arkcluster")  # type: ignore[arg-type]
@kopf.on.create("arkcluster")
async def on_create_data_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    patch = kwargs["patch"]
    if status.initalized or status.is_stage_completed(ClusterStage.DATA_PVC):
        return

    logger = kwargs["logger"]
    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE
    spec = ArkClusterSpec(**kwargs["spec"])

    try:
        await update_data_pvc(
            name=name,
            namespace=namespace,
            spec=spec.data,
            logger=logger,
            warn_existing=True,
        )
    except kopf.PermanentError as ex:
        patch.status["state"] = f"Error: {ex!s}"
        raise

    patch.status["stages"] = status.mark_stage_complete(ClusterStage.DATA_PVC)


@kopf.on.resume("arkcluster")  # type: ignore[arg-type]
@kopf.on.create("arkcluster")
async def on_create_init_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    if status.initalized or status.is_stage_completed(ClusterStage.INIT_PVC):
        return

    if not status.is_stage_completed(
        ClusterStage.SERVER_PVC
    ) or not status.is_stage_completed(ClusterStage.DATA_PVC):
        raise kopf.TemporaryError(ERROR_WAIT_PVC, delay=1)

    logger = kwargs["logger"]
    patch = kwargs["patch"]
    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE
    spec = ArkClusterSpec(**kwargs["spec"])

    try:
        job_result = await check_init_job(name=name, namespace=namespace, logger=logger)
        if not job_result:
            logger.info("Init job does not exist yet, creating it")
            await create_init_job(
                name=name,
                namespace=namespace,
                spec=spec,
                status=status,
                logger=logger,
                dry_run=DRY_RUN,
            )
            raise kopf.TemporaryError(ERROR_WAIT_INIT_JOB, delay=30)
    except kopf.PermanentError as ex:
        patch.status["state"] = f"Error: {ex!s}"
        raise

    if DRY_RUN:
        latest_version = 1
    else:
        steam = Steam(Path(gettempdir()) / "steam")
        latest_version = await steam.get_latest_ark_buildid()
    patch.status["activeVolume"] = "server-a"
    patch.status["activeBuildid"] = latest_version
    patch.status["latestBuildid"] = latest_version
    patch.status["stages"] = status.mark_stage_complete(ClusterStage.INIT_PVC)


@kopf.on.resume("arkcluster")  # type: ignore[arg-type]
@kopf.on.create("arkcluster")
async def on_create_resources(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    patch = kwargs["patch"]
    if status.is_stage_completed(ClusterStage.CREATE):
        return

    if not (status.initalized or status.is_stage_completed(ClusterStage.INIT_PVC)):
        raise kopf.TemporaryError(ERROR_WAIT_INIT_JOB, delay=1)

    logger = kwargs["logger"]
    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE
    spec = ArkClusterSpec(**kwargs["spec"])
    tasks = [create_secrets(name=name, namespace=namespace, logger=logger)]

    try:
        await asyncio.gather(*tasks)
        await asyncio.gather(
            *[
                create_server_pod(
                    name=name,
                    namespace=namespace,
                    map_id=m,
                    active_volume=status.active_volume or "server-a",
                    spec=spec,
                    logger=logger,
                    dry_run=DRY_RUN,
                    force_create=True,
                )
                for m in spec.server.active_maps
            ]
        )
    except kopf.PermanentError as ex:
        patch.status["state"] = f"Error: {ex!s}"
        raise

    patch.status["stages"] = status.mark_stage_complete(ClusterStage.CREATE)
