"""Main handlers for kopf."""

import asyncio
from typing import Unpack

import kopf

from ark_operator.ark import create_server_pod, update_data_pvc, update_server_pvc
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
    ERROR_WAIT_PVC,
)


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

    if not status.ready:
        status.state = "Updating Resources"
        patch = kwargs["patch"]
        patch.status.update(**status.model_dump(include={"state", "ready"}))
        raise kopf.TemporaryError(ERROR_WAIT_PVC, delay=3)

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


@kopf.on.update("arkcluster")  # type: ignore[arg-type]
async def on_update_resources(**kwargs: Unpack[ChangeEvent]) -> None:
    """Update an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    if status.ready:
        return

    logger = kwargs["logger"]
    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE
    spec = ArkClusterSpec(**kwargs["spec"])

    try:
        await asyncio.gather(
            *[
                create_server_pod(
                    name=name,
                    namespace=namespace,
                    map_id=m,
                    active_volume=status.active_volume or "server-a",
                    spec=spec,
                    logger=logger,
                    force_create=True,
                    dry_run=DRY_RUN,
                )
                for m in spec.server.active_maps
            ]
        )
    except kopf.PermanentError as ex:
        kwargs["patch"].status["state"] = f"Error: {ex!s}"
        raise

    kwargs["patch"].status["ready"] = status.mark_stage_complete(ClusterStage.DATA_PVC)
