"""Main handlers for kopf."""

import asyncio
from typing import Unpack

import kopf
from environs import Env

from ark_operator.ark import (
    check_init_job,
    create_init_job,
    delete_check_update_cron_job,
    update_check_update_cron_job,
    update_data_pvc,
    update_server_pvc,
)
from ark_operator.data import (
    ActivityEvent,
    ArkClusterSpec,
    ArkClusterStatus,
    ChangeEvent,
    ClusterStage,
)
from ark_operator.k8s import delete_pvc, get_k8s_client

_ENV = Env()
DRY_RUN = _ENV.bool("ARK_OP_KOPF_DRY_RUN", _ENV.bool("ARK_OP_DRY_RUN", False))
DEFAULT_NAME = "ark"
DEFAULT_NAMESPACE = "default"
ERROR_WAIT_PVC = "Waiting for PVC to complete"
ERROR_WAIT_INIT_POD = "Waiting for volume init pod to completed."
ERROR_WAIT_INIT_RESOURCES = "Waiting for resources to be created."


@kopf.on.startup()  # type: ignore[arg-type]
async def startup(**_: Unpack[ActivityEvent]) -> None:
    """Kopf startup handler."""

    await get_k8s_client()


@kopf.on.cleanup()  # type: ignore[arg-type]
async def cleanup(**_: Unpack[ActivityEvent]) -> None:
    """Kopf cleanup handler."""

    client = await get_k8s_client()
    await client.close()


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
    if retry > 0 and status.is_error:
        patch.status["stages"] = None
        raise kopf.PermanentError

    server_done = status.is_stage_completed(ClusterStage.SERVER_PVC)
    data_done = status.is_stage_completed(ClusterStage.DATA_PVC)
    if not server_done or not data_done:
        status.state = "Creating PVCs"
        patch = kwargs["patch"]
        patch.status.update(**status.model_dump(include={"state", "ready"}))
        raise kopf.TemporaryError(ERROR_WAIT_PVC, delay=3)

    init_done = status.is_stage_completed(ClusterStage.INIT_PVC)
    if server_done and data_done and not init_done:
        status.state = "Initializing PVCs"
        patch = kwargs["patch"]
        patch.status.update(**status.model_dump(include={"state", "ready"}))
        raise kopf.TemporaryError(ERROR_WAIT_PVC, delay=30)

    all_initialized = all([server_done, data_done, init_done])
    create_done = status.is_stage_completed(ClusterStage.CREATE)
    if all_initialized and not create_done:
        status.state = "Creating Resources"
        patch = kwargs["patch"]
        patch.status.update(**status.model_dump(include={"state", "ready"}))
        raise kopf.TemporaryError(ERROR_WAIT_INIT_RESOURCES, delay=3)

    status.ready = True
    status.state = "Running"
    patch = kwargs["patch"]
    patch.status.update(**status.model_dump(include={"state", "ready"}))
    patch.status["stages"] = None


@kopf.on.resume("arkcluster")  # type: ignore[arg-type]
@kopf.on.create("arkcluster")
async def on_create_server_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    if status.is_stage_completed(ClusterStage.SERVER_PVC):
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
        kwargs["patch"].status["state"] = f"Error: {ex!s}"
        raise

    kwargs["patch"].status["stages"] = status.mark_stage_complete(
        ClusterStage.SERVER_PVC
    )


@kopf.on.resume("arkcluster")  # type: ignore[arg-type]
@kopf.on.create("arkcluster")
async def on_create_data_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    if status.is_stage_completed(ClusterStage.DATA_PVC):
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
        kwargs["patch"].status["state"] = f"Error: {ex!s}"
        raise

    kwargs["patch"].status["stages"] = status.mark_stage_complete(ClusterStage.DATA_PVC)


@kopf.on.resume("arkcluster")  # type: ignore[arg-type]
@kopf.on.create("arkcluster")
async def on_create_init_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    if status.is_stage_completed(ClusterStage.INIT_PVC):
        return

    if not status.is_stage_completed(
        ClusterStage.SERVER_PVC
    ) or not status.is_stage_completed(ClusterStage.DATA_PVC):
        raise kopf.TemporaryError(ERROR_WAIT_PVC, delay=1)

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
                logger=logger,
                dry_run=DRY_RUN,
            )
            raise kopf.TemporaryError(ERROR_WAIT_INIT_POD, delay=30)
    except kopf.PermanentError as ex:
        kwargs["patch"].status["state"] = f"Error: {ex!s}"
        raise

    kwargs["patch"].status["stages"] = status.mark_stage_complete(ClusterStage.INIT_PVC)


@kopf.on.resume("arkcluster")  # type: ignore[arg-type]
@kopf.on.create("arkcluster")
async def on_create_resources(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    if status.is_stage_completed(ClusterStage.CREATE):
        return

    if not status.is_stage_completed(ClusterStage.INIT_PVC):
        raise kopf.TemporaryError(ERROR_WAIT_INIT_POD, delay=1)

    logger = kwargs["logger"]
    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE
    spec = ArkClusterSpec(**kwargs["spec"])

    try:
        await update_check_update_cron_job(
            name=name,
            namespace=namespace,
            active_volume="server-a",
            spec=spec,
            logger=logger,
            do_update=False,
        )
    except kopf.PermanentError as ex:
        kwargs["patch"].status["state"] = f"Error: {ex!s}"
        raise

    kwargs["patch"].status["stages"] = status.mark_stage_complete(ClusterStage.CREATE)


@kopf.on.update("arkcluster")  # type: ignore[arg-type]
async def on_update_state(**kwargs: Unpack[ChangeEvent]) -> None:
    """Update an ARKCluster."""

    patch = kwargs["patch"]
    retry = kwargs["retry"]
    status = ArkClusterStatus(**kwargs["status"])
    if retry > 0 and status.is_error:
        patch.status["stages"] = None
        raise kopf.PermanentError

    server_done = status.is_stage_completed(ClusterStage.SERVER_PVC)
    data_done = status.is_stage_completed(ClusterStage.DATA_PVC)
    if not server_done or not data_done:
        status.ready = False
        status.state = "Updating PVCs"
        patch = kwargs["patch"]
        patch.status.update(**status.model_dump(include={"state", "ready"}))
        raise kopf.TemporaryError(ERROR_WAIT_PVC, delay=3)

    status.ready = True
    status.state = "Running"
    patch = kwargs["patch"]
    patch.status.update(**status.model_dump(include={"state", "ready"}))
    patch.status["stages"] = None


@kopf.on.update("arkcluster")  # type: ignore[arg-type]
async def on_update_server_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Update an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    if status.is_stage_completed(ClusterStage.SERVER_PVC):
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
        kwargs["patch"].status["state"] = f"Error: {ex!s}"
        raise

    kwargs["patch"].status["stages"] = status.mark_stage_complete(
        ClusterStage.SERVER_PVC
    )


@kopf.on.update("arkcluster")  # type: ignore[arg-type]
async def on_update_data_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Update an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    if status.is_stage_completed(ClusterStage.DATA_PVC):
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
            warn_existing=False,
        )
    except kopf.PermanentError as ex:
        kwargs["patch"].status["state"] = f"Error: {ex!s}"
        raise

    kwargs["patch"].status["stages"] = status.mark_stage_complete(ClusterStage.DATA_PVC)


@kopf.on.delete("arkcluster")  # type: ignore[arg-type]
async def on_delete_server_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Delete an ARKCluster."""

    logger = kwargs["logger"]
    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE
    spec = ArkClusterSpec(**kwargs["spec"])

    if not spec.server.persist:
        await delete_pvc(
            name=f"{name}-server-a",
            namespace=namespace,
            logger=logger,
        )
        await delete_pvc(
            name=f"{name}-server-b",
            namespace=namespace,
            logger=logger,
        )


@kopf.on.delete("arkcluster")  # type: ignore[arg-type]
async def on_delete_data_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Delete an ARKCluster."""

    logger = kwargs["logger"]
    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE
    spec = ArkClusterSpec(**kwargs["spec"])

    if not spec.data.persist:
        await delete_pvc(
            name=f"{name}-data",
            namespace=namespace,
            logger=logger,
        )


@kopf.on.delete("arkcluster")  # type: ignore[arg-type]
async def on_delete_resources(**kwargs: Unpack[ChangeEvent]) -> None:
    """Delete an ARKCluster."""

    logger = kwargs["logger"]
    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE

    await asyncio.gather(
        check_init_job(
            name=name, namespace=namespace, logger=logger, force_delete=True
        ),
        delete_check_update_cron_job(name=name, namespace=namespace, logger=logger),
    )
