"""Create handlers for kopf."""

import asyncio
from datetime import timedelta
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
    get_active_buildid,
    get_active_version,
    get_active_volume,
    restart_server_pods,
    shutdown_server_pods,
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
    ERROR_RESTARTING,
    ERROR_WAIT_INIT_JOB,
    ERROR_WAIT_INIT_RESOURCES,
    ERROR_WAIT_PVC,
    restart_with_lock,
)
from ark_operator.steam import Steam
from ark_operator.utils import utc_now


def _update_state(
    status: ArkClusterStatus, patch: kopf.Patch, state: str = "Creating Resources"
) -> None:
    if status.ready or status.state != state:
        status.ready = False
        status.state = state
        patch.status.update(
            **status.model_dump(include={"state", "ready"}, by_alias=True)
        )
        raise kopf.TemporaryError(ERROR_WAIT_INIT_RESOURCES, delay=1)


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

    if status.restart is not None:
        raise kopf.TemporaryError(ERROR_RESTARTING, delay=30)
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
async def on_create_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    patch = kwargs["patch"]
    logger = kwargs["logger"]

    if status.restart is not None:
        raise kopf.TemporaryError(ERROR_RESTARTING, delay=30)
    if status.initalized or status.is_stage_completed(ClusterStage.CREATE_PVC):
        return
    _update_state(status, patch)

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

    status.mark_stage_complete(ClusterStage.CREATE_PVC)
    patch.status.update(**status.model_dump(include={"stages"}, by_alias=True))
    logger.debug("status update %s", patch.status)


@kopf.on.resume("arkcluster")  # type: ignore[arg-type]
@kopf.on.create("arkcluster")
async def on_create_init_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    patch = kwargs["patch"]

    if status.restart is not None:
        raise kopf.TemporaryError(ERROR_RESTARTING, delay=30)
    if status.initalized or status.is_stage_completed(ClusterStage.INIT_PVC):
        status.initalized = True
        patch.status.update(**status.model_dump(include={"initialized"}, by_alias=True))
        return

    if not status.is_stage_completed(ClusterStage.CREATE_PVC):
        raise kopf.TemporaryError(ERROR_WAIT_PVC, delay=1)
    _update_state(status, patch, state="Initializing PVCs")

    logger = kwargs["logger"]
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
    status.initalized = True
    patch.status.update(
        **status.model_dump(
            include={
                "active_volume",
                "active_buildid",
                "latest_buildid",
                "stages",
                "initialized",
            },
            by_alias=True,
        )
    )
    logger.debug("status update %s", patch.status)


def _mark_ready(
    status: ArkClusterStatus, patch: kopf.Patch, logger: kopf.Logger
) -> None:
    status.initalized = True
    status.ready = True
    status.state = "Running"
    status.stages = None
    patch.status.update(
        **status.model_dump(
            include={"initalized", "state", "ready", "stages", "last_applied_version"},
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
    logger = kwargs["logger"]
    is_resume = status.last_applied_version is not None or reason == kopf.Reason.RESUME

    if status.restart is not None:
        raise kopf.TemporaryError(ERROR_RESTARTING, delay=30)
    if status.ready:
        _mark_ready(status, patch, logger)
        return

    if not (status.initalized or status.is_stage_completed(ClusterStage.INIT_PVC)):
        raise kopf.TemporaryError(ERROR_WAIT_INIT_JOB, delay=1)
    _update_state(status, patch)

    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE
    spec = ArkClusterSpec(**kwargs["spec"])
    tasks = [
        create_secrets(name=name, namespace=namespace, logger=logger),
        create_services(name=name, namespace=namespace, spec=spec, logger=logger),
    ]

    logger.debug("cluster spec: %s", spec)
    active_volume = status.active_volume or await get_active_volume(
        name=name, namespace=namespace, spec=spec
    )

    try:
        await asyncio.gather(*tasks)
        last_version = status.last_applied_version or get_active_version(
            name=name, namespace=namespace, spec=spec
        )
        if is_resume and last_version != ARK_SERVER_IMAGE_VERSION:
            old = status.last_applied_version
            new = ARK_SERVER_IMAGE_VERSION
            logger.info("Container version mismatch (%s -> %s)", old, new)
            await restart_with_lock(
                name=name,
                namespace=namespace,
                spec=spec,
                active_volume=active_volume,
                active_buildid=status.active_buildid,
                reason="container update",
                logger=logger,
                dry_run=DRY_RUN,
                trigger_time=kwargs["started"],
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
    _mark_ready(status, patch, logger)


@kopf.on.resume("arkcluster")  # type: ignore[arg-type]
async def on_resume_restart(**kwargs: Unpack[ChangeEvent]) -> None:
    """Resume handler to resume restart/shutdowns."""

    status = ArkClusterStatus(**kwargs["status"])

    if not status.restart:
        return

    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE
    spec = ArkClusterSpec(**kwargs["spec"])
    logger = kwargs["logger"]

    wait_interval = timedelta(seconds=0)
    if status.restart.time:
        now = utc_now()
        if now > status.restart.time:
            wait_interval = timedelta(seconds=10)
        else:
            wait_interval = status.restart.time - now

    logger.info(
        "Resuming %s (%s): %s", status.restart.type, wait_interval, status.restart
    )
    if status.restart.type == "shutdown":
        await shutdown_server_pods(
            name=name,
            namespace=namespace,
            spec=spec,
            reason=status.restart.reason,
            logger=logger,
            servers=status.restart.maps,
            wait_interval=wait_interval,
        )
    else:
        active_volume = (
            status.restart.active_volume
            or status.active_volume
            or await get_active_volume(name=name, namespace=namespace, spec=spec)
        )
        active_buildid = (
            status.restart.active_buildid
            or status.active_buildid
            or await get_active_buildid(name=name, namespace=namespace, spec=spec)
        )
        # restart interrupted pod restarts
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
                )
                for m in spec.server.active_maps
            ]
        )
        # resume restart
        await restart_server_pods(
            name=name,
            namespace=namespace,
            spec=spec,
            reason=status.restart.reason,
            logger=logger,
            servers=status.restart.maps,
            wait_interval=wait_interval,
            active_volume=active_volume,
            active_buildid=active_buildid,
        )
