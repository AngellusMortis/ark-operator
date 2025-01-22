"""Create handlers for kopf."""

import asyncio
from pathlib import Path
from tempfile import gettempdir
from typing import Unpack

import kopf

from ark_operator.ark import (
    ARK_SERVER_IMAGE_VERSION,
    check_init_job,
    create_init_job,
    create_secrets,
    create_server_pod,
    create_services,
    get_active_volume,
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
    add_tracked_instance,
    restart_with_lock,
)
from ark_operator.steam import Steam


@kopf.on.resume("arkcluster")  # type: ignore[arg-type]
@kopf.on.create("arkcluster")
async def on_create_init(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    patch = kwargs["patch"]
    logger = kwargs["logger"]
    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE
    spec = ArkClusterSpec(**kwargs["spec"])

    if not status.state and not status.ready and not status.initalized:
        patch.status.update(status.model_dump(by_alias=True))
        logger.debug("status update %s", patch.status)
        return

    if status.active_volume is None:
        status.active_volume = await get_active_volume(
            name=name, namespace=namespace, spec=spec
        )
        patch.status.update(
            **status.model_dump(include={"active_volume"}, by_alias=True)
        )
        logger.debug("status update %s", patch.status)
    if status.active_buildid is None:
        status.active_buildid = status.latest_buildid
        patch.status.update(
            **status.model_dump(include={"active_buildid"}, by_alias=True)
        )
        logger.debug("status update %s", patch.status)


@kopf.on.resume("arkcluster")  # type: ignore[arg-type]
@kopf.on.create("arkcluster")
async def on_create_state(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    add_tracked_instance(kwargs["name"], kwargs["namespace"])

    patch = kwargs["patch"]
    retry = kwargs["retry"]
    logger = kwargs["logger"]
    status = ArkClusterStatus(**kwargs["status"])
    status.ready = status.ready or False

    if retry == 0:
        status.ready = False
        status.stages = None
        patch.status.update(
            **status.model_dump(include={"state", "ready", "stages"}, by_alias=True)
        )
        logger.debug("status update %s", patch.status)
    elif status.ready:
        status.state = "Running"
        status.stages = None
        status.initalized = True
        patch.status.update(
            **status.model_dump(
                include={"state", "ready", "stages", "initialized"}, by_alias=True
            )
        )
        logger.debug("status update %s", patch.status)
        return

    if retry > 0 and status.is_error:
        status.stages = None
        patch.status.update(**status.model_dump(include={"stages"}, by_alias=True))
        logger.debug("status update %s", patch.status)
        raise kopf.PermanentError

    server_done = status.initalized or status.is_stage_completed(
        ClusterStage.SERVER_PVC
    )
    data_done = status.initalized or status.is_stage_completed(ClusterStage.DATA_PVC)
    if not server_done or not data_done:
        status.state = "Creating PVCs"
        patch.status.update(
            **status.model_dump(include={"state", "ready"}, by_alias=True)
        )
        logger.debug("status update %s", patch.status)
        raise kopf.TemporaryError(ERROR_WAIT_PVC, delay=3)

    init_done = status.initalized or status.is_stage_completed(ClusterStage.INIT_PVC)
    if server_done and data_done and not init_done:
        status.state = "Initializing PVCs"
        patch.status.update(
            **status.model_dump(include={"state", "ready"}, by_alias=True)
        )
        logger.debug("status update %s", patch.status)
        raise kopf.TemporaryError(ERROR_WAIT_PVC, delay=30)

    all_initialized = status.initalized or all([server_done, data_done, init_done])
    create_done = status.is_stage_completed(ClusterStage.CREATE)
    if all_initialized and not create_done:
        status.state = "Creating Resources"
        patch.status.update(
            **status.model_dump(include={"state", "ready"}, by_alias=True)
        )
        logger.debug("status update %s", patch.status)
        raise kopf.TemporaryError(ERROR_WAIT_INIT_RESOURCES, delay=3)

    status.ready = True
    status.state = "Running"
    status.stages = None
    status.initalized = True
    patch.status.update(
        **status.model_dump(
            include={"state", "ready", "stages", "initialized"}, by_alias=True
        )
    )
    logger.debug("status update %s", patch.status)


@kopf.on.resume("arkcluster")  # type: ignore[arg-type]
@kopf.on.create("arkcluster")
async def on_create_server_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    patch = kwargs["patch"]
    logger = kwargs["logger"]
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
        logger.debug("status update %s", patch.status)
        raise

    patch.status["stages"] = status.mark_stage_complete(ClusterStage.SERVER_PVC)
    logger.debug("status update %s", patch.status)


@kopf.on.resume("arkcluster")  # type: ignore[arg-type]
@kopf.on.create("arkcluster")
async def on_create_data_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    patch = kwargs["patch"]
    logger = kwargs["logger"]
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
        logger.debug("status update %s", patch.status)
        raise

    patch.status["stages"] = status.mark_stage_complete(ClusterStage.DATA_PVC)
    logger.debug("status update %s", patch.status)


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
        logger.debug("status update %s", patch.status)
        raise

    if DRY_RUN:
        latest_version = 1
    else:
        steam = Steam(Path(gettempdir()) / "steam")
        latest_version = await steam.get_latest_ark_buildid()

    status.active_volume = "server-a"
    status.active_buildid = latest_version
    status.latest_buildid = latest_version
    status.mark_stage_complete(ClusterStage.INIT_PVC)
    patch.status.update(
        **status.model_dump(
            include={"active_volume", "active_buildid", "latest_buildid", "stages"},
            by_alias=True,
        )
    )
    logger.debug("status update %s", patch.status)


@kopf.on.resume("arkcluster")  # type: ignore[arg-type]
@kopf.on.create("arkcluster")
async def on_create_resources(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    patch = kwargs["patch"]
    reason = kwargs["reason"]
    is_resume = status.last_applied_version is not None or reason == kopf.Reason.RESUME
    if status.is_stage_completed(ClusterStage.CREATE):
        return

    if not (status.initalized or status.is_stage_completed(ClusterStage.INIT_PVC)):
        raise kopf.TemporaryError(ERROR_WAIT_INIT_JOB, delay=1)

    logger = kwargs["logger"]
    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE
    spec = ArkClusterSpec(**kwargs["spec"])
    tasks = [
        create_secrets(name=name, namespace=namespace, logger=logger),
        create_services(name=name, namespace=namespace, spec=spec, logger=logger),
    ]

    logger.debug("cluster spec: %s", spec)
    try:
        await asyncio.gather(*tasks)
        if is_resume and status.last_applied_version != ARK_SERVER_IMAGE_VERSION:
            old = status.last_applied_version
            new = ARK_SERVER_IMAGE_VERSION
            logger.info("Container version mismatch (%s -> %s)", old, new)
            active_volume = status.active_volume or await get_active_volume(
                name=name, namespace=namespace, spec=spec
            )
            await restart_with_lock(
                name=name,
                namespace=namespace,
                spec=spec,
                active_volume=active_volume,
                active_buildid=status.active_buildid,
                reason="container update",
                logger=logger,
                dry_run=DRY_RUN,
            )
        await asyncio.gather(
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
                    force_create=True,
                )
                for m in spec.server.active_maps
            ]
        )
    except kopf.PermanentError as ex:
        patch.status["state"] = f"Error: {ex!s}"
        logger.debug("status update %s", patch.status)
        raise

    status.last_applied_version = ARK_SERVER_IMAGE_VERSION
    status.mark_stage_complete(ClusterStage.CREATE)
    patch.status.update(
        **status.model_dump(
            include={"last_applied_version", "stages"},
            by_alias=True,
        )
    )
    logger.debug("status update %s", patch.status)
