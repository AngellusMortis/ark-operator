"""Main handlers for kopf."""

import asyncio
from typing import Unpack

import kopf

from ark_operator.ark import (
    create_server_pod,
    create_services,
    get_active_volume,
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
    ERROR_WAIT_PVC,
    ERROR_WAIT_UPDATE_JOB,
    add_tracked_instance,
    is_restarting,
    restart_with_lock,
)

FIELDS_PVC_UPDATE = {
    ("spec", "data", "storageClass"),
    ("spec", "data", "size"),
    ("spec", "server", "storageClass"),
    ("spec", "server", "size"),
}
FIELDS_NO_SERVER_UPDATE = {
    ("spec", "data", "persist"),
    ("spec", "service", "loadBalancerIP"),
    ("spec", "server", "loadBalancerIP"),
    ("spec", "server", "gracefulShutdown"),
    ("spec", "server", "shutdownMessageFormat"),
    ("spec", "server", "persist"),
}


@kopf.on.update("arkcluster")  # type: ignore[arg-type]
async def on_update_state(**kwargs: Unpack[ChangeEvent]) -> None:
    """Update an ARKCluster."""

    add_tracked_instance(kwargs["name"], kwargs["namespace"])

    patch = kwargs["patch"]
    retry = kwargs["retry"]
    logger = kwargs["logger"]
    status = ArkClusterStatus(**kwargs["status"])
    status.ready = status.ready or False

    if is_restarting(status):
        raise kopf.TemporaryError(ERROR_RESTARTING, delay=30)

    if retry == 0:
        status.ready = False
        status.stages = None
        patch.status.update(
            **status.model_dump(include={"stages", "state", "ready"}, by_alias=True)
        )
        logger.debug("status update %s", patch.status)
    elif status.ready:
        status.state = "Running"
        status.stages = None
        patch.status.update(
            **status.model_dump(include={"stages", "state", "ready"}, by_alias=True)
        )
        logger.debug("status update %s", patch.status)
        return

    if retry > 0 and status.is_error:
        status.stages = None
        patch.status.update(**status.model_dump(include={"stages"}, by_alias=True))
        logger.debug("status update %s", patch.status)
        raise kopf.PermanentError

    server_done = status.is_stage_completed(ClusterStage.SERVER_PVC)
    data_done = status.is_stage_completed(ClusterStage.DATA_PVC)
    if not server_done or not data_done:
        status.state = "Updating PVCs"
        patch.status.update(
            **status.model_dump(include={"state", "ready"}, by_alias=True)
        )
        logger.debug("status update %s", patch.status)
        raise kopf.TemporaryError(ERROR_WAIT_PVC, delay=3)

    if not status.ready:
        status.state = "Updating Resources"
        patch.status.update(
            **status.model_dump(include={"state", "ready"}, by_alias=True)
        )
        logger.debug("status update %s", patch.status)
        raise kopf.TemporaryError(ERROR_WAIT_UPDATE_JOB, delay=3)

    status.state = "Running"
    status.stages = None
    patch.status.update(
        **status.model_dump(include={"stages", "state", "ready"}, by_alias=True)
    )
    logger.debug("status update %s", patch.status)


@kopf.on.update("arkcluster")  # type: ignore[arg-type]
async def on_update_server_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Update an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    patch = kwargs["patch"]

    if is_restarting(status):
        raise kopf.TemporaryError(ERROR_RESTARTING, delay=30)
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
        logger.debug("status update %s", patch.status)
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
        logger.debug("status update %s", patch.status)
        raise

    patch.status["stages"] = status.mark_stage_complete(ClusterStage.SERVER_PVC)
    logger.debug("status update %s", patch.status)


@kopf.on.update("arkcluster")  # type: ignore[arg-type]
async def on_update_data_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Update an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    patch = kwargs["patch"]

    if is_restarting(status):
        raise kopf.TemporaryError(ERROR_RESTARTING, delay=30)
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
        logger.debug("status update %s", patch.status)
        raise

    patch.status["stages"] = status.mark_stage_complete(ClusterStage.DATA_PVC)
    logger.debug("status update %s", patch.status)


async def _restart_servers(  # noqa: PLR0913
    *,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
    logger: kopf.Logger,
    patch: kopf.Patch,
    active_volume: str,
    active_buildid: int | None,
    restart: bool,
) -> None:
    try:
        if restart:
            await restart_with_lock(
                name=name,
                namespace=namespace,
                spec=spec,
                reason="configuration update",
                active_volume=active_volume,
                active_buildid=active_buildid,
                logger=logger,
                dry_run=DRY_RUN,
            )
        else:
            await shutdown_server_pods(
                name=name,
                namespace=namespace,
                spec=spec,
                reason="cluster update",
                logger=logger,
            )
            logger.info("Waiting 30 seconds before starting back up pods")
            await asyncio.sleep(30)
    except kopf.PermanentError as ex:
        patch.status["state"] = f"Error: {ex!s}"
        logger.debug("status update %s", patch.status)
        raise


@kopf.on.update("arkcluster")  # type: ignore[arg-type]
async def on_update_resources(**kwargs: Unpack[ChangeEvent]) -> None:
    """Update an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    patch = kwargs["patch"]

    if is_restarting(status):
        raise kopf.TemporaryError(ERROR_RESTARTING, delay=30)
    if (
        status.is_stage_completed(ClusterStage.DATA_PVC)
        and status.is_stage_completed(ClusterStage.SERVER_PVC)
        and status.ready
    ):
        return

    logger = kwargs["logger"]
    diff = kwargs["diff"]
    update_servers = False
    allow_restart = True
    for change in diff:
        if change.field[0] != "spec":
            continue
        if change.field not in FIELDS_NO_SERVER_UPDATE:
            logger.info("Update servers do to field update: %s", change.field)
            update_servers = True
            # if there is only updates to global settings,
            # rolling restart is acceptable and better
            if change.field[1] != "globalSettings":
                allow_restart = False
            break

    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE
    spec = ArkClusterSpec(**kwargs["spec"])

    await create_services(name=name, namespace=namespace, spec=spec, logger=logger)

    logger.debug("cluster spec: %s", spec)
    if not update_servers:
        status.ready = True
        patch.status.update(**status.model_dump(include={"ready"}, by_alias=True))
        logger.debug("status update %s", patch.status)
        return

    active_volume = status.active_volume or await get_active_volume(
        name=name, namespace=namespace, spec=spec
    )
    try:
        await _restart_servers(
            name=name,
            namespace=namespace,
            spec=spec,
            logger=logger,
            active_volume=active_volume,
            active_buildid=status.active_buildid,
            patch=patch,
            restart=allow_restart,
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
                    force_create=True,
                    dry_run=DRY_RUN,
                )
                for m in spec.server.active_maps
            ]
        )
    except kopf.PermanentError as ex:
        patch.status["state"] = f"Error: {ex!s}"
        logger.debug("status update %s", patch.status)
        raise

    status.ready = True
    patch.status.update(**status.model_dump(include={"ready"}, by_alias=True))
    logger.debug("status update %s", patch.status)
