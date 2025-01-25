"""Main handlers for kopf."""

import asyncio
from datetime import datetime
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
    ERROR_UPDATE_STATUS,
    ERROR_WAIT_INIT_RESOURCES,
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
    ("spec", "service"),
    ("spec", "service", "loadBalancerIP"),
    ("spec", "service", "annotations"),
    ("spec", "server"),
    ("spec", "server", "gracefulShutdown"),
    ("spec", "server", "shutdownMessageFormat"),
    ("spec", "server", "restartMessageFormat"),
    ("spec", "server", "restartStartMessage"),
    ("spec", "server", "rollingRestartFormat"),
    ("spec", "server", "restartCompleteMessage"),
    ("spec", "server", "persist"),
    ("spec", "server", "suspend"),
}


def _update_state(status: ArkClusterStatus, patch: kopf.Patch) -> None:
    if status.ready:
        status.ready = False
        status.state = "Updating Resources"
        patch.status.update(**status.model_dump(include={"state", "ready"}))
        raise kopf.TemporaryError(ERROR_UPDATE_STATUS, delay=1)


@kopf.on.update("arkcluster")  # type: ignore[arg-type]
async def on_update_pvc(**kwargs: Unpack[ChangeEvent]) -> None:
    """Update an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    patch = kwargs["patch"]

    if status.restart is not None:
        raise kopf.TemporaryError(ERROR_RESTARTING, delay=30)
    if status.is_stage_completed(ClusterStage.UPDATE_PVC):
        return
    _update_state(status, patch)

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
        status.mark_stage_complete(ClusterStage.UPDATE_PVC)
        patch.status.update(**status.model_dump(include={"stages"}))
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

    status.mark_stage_complete(ClusterStage.UPDATE_PVC)
    patch.status.update(**status.model_dump(include={"stages"}))
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
    trigger_time: datetime,
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
                trigger_time=trigger_time,
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
            await asyncio.gather(
                *[
                    create_server_pod(
                        name=name,
                        namespace=namespace,
                        map_id=m,
                        active_volume=active_volume,
                        active_buildid=active_buildid,
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


def _mark_ready(
    status: ArkClusterStatus, patch: kopf.Patch, logger: kopf.Logger
) -> None:
    status.ready = True
    status.state = "Running"
    status.stages = None
    patch.status.update(**status.model_dump(include={"ready", "state", "stages"}))
    logger.debug("status update %s", patch.status)


@kopf.on.update("arkcluster")  # type: ignore[arg-type]
async def on_update_resources(**kwargs: Unpack[ChangeEvent]) -> None:  # noqa: C901
    """Update an ARKCluster."""

    status = ArkClusterStatus(**kwargs["status"])
    patch = kwargs["patch"]
    logger = kwargs["logger"]

    if status.restart is not None:
        raise kopf.TemporaryError(ERROR_RESTARTING, delay=30)
    if not status.is_stage_completed(ClusterStage.UPDATE_PVC):
        raise kopf.TemporaryError(ERROR_WAIT_INIT_RESOURCES, delay=30)
    _update_state(status, patch)

    diff = kwargs["diff"]
    update_servers = False
    allow_restart = True
    for change in diff:
        if change.field[0] != "spec":
            continue
        if change.operation == "add" and change.old is None and change.new is not None:
            logger.info("Skipping field change because default value: %s", change)
            continue
        if change.old in [None, []] and change.new in [None, []]:
            logger.info("Skipping field change because nothing was changed: %s", change)
            continue
        if change.field not in FIELDS_NO_SERVER_UPDATE:
            logger.info("Update servers due to field update: %s", change)
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
        _mark_ready(status, patch, logger)
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

    _mark_ready(status, patch, logger)
