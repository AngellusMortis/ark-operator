"""Main handlers for kopf."""

from typing import Unpack

import kopf

from ark_operator.ark import (
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

DEFAULT_NAME = "ark"
DEFAULT_NAMESPACE = "default"
ERROR_WAIT_PVC = "Waiting for PVC to complete"


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
        kwargs["patch"].status["state"] = str(ex)
        raise

    kwargs["patch"].status["stages"] = status.mark_stage_complete(ClusterStage.DATA_PVC)


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
