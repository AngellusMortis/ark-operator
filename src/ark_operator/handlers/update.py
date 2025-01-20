"""Main handlers for kopf."""

import asyncio
from typing import Unpack

import kopf

from ark_operator.ark import (
    create_server_pod,
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
    ERROR_WAIT_PVC,
    ERROR_WAIT_UPDATE_JOB,
)

FIELDS_PVC_UPDATE = [
    ("spec", "data", "storageClass"),
    ("spec", "data", "size"),
    ("spec", "server", "storageClass"),
    ("spec", "server", "size"),
]
FIELDS_NO_SERVER_UPDATE = [
    ("spec", "data", "persist"),
    ("spec", "server", "loadBalancerIP"),
    ("spec", "server", "gracefulShutdown"),
    ("spec", "server", "shutdownMessageFormat"),
    ("spec", "server", "persist"),
]


@kopf.on.update("arkcluster")  # type: ignore[arg-type]
async def on_update_state(**kwargs: Unpack[ChangeEvent]) -> None:
    """Update an ARKCluster."""

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
        return

    if retry > 0 and status.is_error:
        patch.status["stages"] = None
        raise kopf.PermanentError

    server_done = status.is_stage_completed(ClusterStage.SERVER_PVC)
    data_done = status.is_stage_completed(ClusterStage.DATA_PVC)
    if not server_done or not data_done:
        status.state = "Updating PVCs"
        patch.status.update(**status.model_dump(include={"state", "ready"}))
        raise kopf.TemporaryError(ERROR_WAIT_PVC, delay=3)

    if not status.ready:
        status.state = "Updating Resources"
        patch.status.update(**status.model_dump(include={"state", "ready"}))
        raise kopf.TemporaryError(ERROR_WAIT_UPDATE_JOB, delay=3)

    status.state = "Running"
    patch.status.update(**status.model_dump(include={"state", "ready"}))
    patch.status["stages"] = None


@kopf.on.update("arkcluster")  # type: ignore[arg-type]
async def on_update_server_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Update an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    patch = kwargs["patch"]
    if status.is_stage_completed(ClusterStage.SERVER_PVC):
        return

    logger = kwargs["logger"]
    diff = kwargs["diff"]

    update_pvc = False
    for change in diff:
        if change.field[0] != "spec":
            continue
        if change.field in FIELDS_PVC_UPDATE and change.field[1] == "server":
            update_pvc = True
            break

    if not update_pvc:
        patch.status["stages"] = status.mark_stage_complete(ClusterStage.SERVER_PVC)
        return

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


@kopf.on.update("arkcluster")  # type: ignore[arg-type]
async def on_update_data_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Update an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    patch = kwargs["patch"]
    if status.is_stage_completed(ClusterStage.DATA_PVC):
        return

    logger = kwargs["logger"]
    diff = kwargs["diff"]

    update_pvc = False
    for change in diff:
        if change.field[0] != "spec":
            continue
        if change.field in FIELDS_PVC_UPDATE and change.field[1] == "data":
            update_pvc = True
            break

    if not update_pvc:
        patch.status["stages"] = status.mark_stage_complete(ClusterStage.DATA_PVC)
        return

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
        patch.status["state"] = f"Error: {ex!s}"
        raise

    patch.status["stages"] = status.mark_stage_complete(ClusterStage.DATA_PVC)


@kopf.on.update("arkcluster")  # type: ignore[arg-type]
async def on_update_resources(**kwargs: Unpack[ChangeEvent]) -> None:
    """Update an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    patch = kwargs["patch"]
    if (
        status.is_stage_completed(ClusterStage.DATA_PVC)
        and status.is_stage_completed(ClusterStage.SERVER_PVC)
        and status.ready
    ):
        return

    logger = kwargs["logger"]
    diff = kwargs["diff"]
    update_servers = False
    for change in diff:
        if change.field[0] != "spec":
            continue
        if change.field not in FIELDS_NO_SERVER_UPDATE:
            update_servers = True
            break

    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE
    spec = ArkClusterSpec(**kwargs["spec"])

    if not update_servers:
        patch.status["ready"] = True
        return

    try:
        await shutdown_server_pods(
            name=name,
            namespace=namespace,
            spec=spec,
            reason="configuration update",
            logger=logger,
        )
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
        patch.status["state"] = f"Error: {ex!s}"
        raise

    patch.status["ready"] = True
