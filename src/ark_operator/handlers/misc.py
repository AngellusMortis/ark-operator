"""Misc handlers for kopf."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from pathlib import Path
from tempfile import gettempdir
from typing import TYPE_CHECKING, Literal, Unpack

import kopf

from ark_operator.ark import (
    check_update_job,
    create_server_pod,
    create_update_job,
    get_server_pod,
    is_server_pod_ready,
)
from ark_operator.data import (
    ActivityEvent,
    ArkClusterSpec,
    ArkClusterStatus,
    TimerEvent,
)
from ark_operator.handlers.utils import (
    DEFAULT_NAME,
    DEFAULT_NAMESPACE,
    DRY_RUN,
    ENV,
    ERROR_WAIT_UPDATE_JOB,
    create_restart_lock,
    restart_with_lock,
)
from ark_operator.k8s import get_k8s_client
from ark_operator.log import DEFAULT_LOG_CONFIG, init_logging
from ark_operator.rcon import close_clients
from ark_operator.steam import Steam

if TYPE_CHECKING:
    from kopf import Patch

ARK_UPDATE_INTERVAL = timedelta(minutes=15).total_seconds()


@kopf.on.startup()  # type: ignore[arg-type]
async def startup(**kwargs: Unpack[ActivityEvent]) -> None:
    """Kopf startup handler."""

    level = ENV("ARK_OP_LOG_LEVEL", "INFO")
    settings = kwargs["settings"]

    settings.posting.level = logging.getLevelNamesMapping()[level]
    init_logging(
        ENV("ARK_OP_LOG_FORMAT", "auto"),
        level,
        config=ENV.dict("ARK_OP_LOG_CONFIG", None) or DEFAULT_LOG_CONFIG,
    )
    create_restart_lock()
    await get_k8s_client()


@kopf.on.cleanup()  # type: ignore[arg-type]
async def cleanup(**kwargs: Unpack[ActivityEvent]) -> None:
    """Kopf cleanup handler."""

    logger = kwargs["logger"]
    client = await get_k8s_client()
    try:
        await client.close()
    except Exception as ex:  # noqa: BLE001
        logger.warning("Failed to close k8s client", exc_info=ex)
    try:
        await close_clients()
    except Exception as ex:  # noqa: BLE001
        logger.warning("Failed to close RCON client(s)", exc_info=ex)


async def _update_server(  # noqa: PLR0913
    *,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
    logger: kopf.Logger,
    status: ArkClusterStatus,
    patch: Patch,
) -> None:
    status.state = "Updating Server"
    status.ready = False
    patch.status.update(**status.model_dump(include={"state", "ready"}, by_alias=True))
    active_volume = status.active_volume or "server-a"
    update_volume: Literal["server-a", "server-b"] = (
        "server-a" if active_volume == "server-b" else "server-b"
    )
    try:
        job_result = await check_update_job(
            name=name, namespace=namespace, logger=logger
        )
        if not job_result:
            logger.info("Update job does not exist yet, creating it")
            await create_update_job(
                name=name,
                namespace=namespace,
                spec=spec,
                logger=logger,
                dry_run=DRY_RUN,
                active_volume=status.active_volume or "server-a",
            )
            raise kopf.TemporaryError(ERROR_WAIT_UPDATE_JOB, delay=30)
    except kopf.PermanentError as ex:
        patch.status["state"] = f"Error: {ex!s}"
        raise

    await restart_with_lock(
        name=name,
        namespace=namespace,
        spec=spec,
        active_volume=status.active_volume or "server-a",
        reason="ARK update",
        logger=logger,
        dry_run=DRY_RUN,
    )

    status.ready = True
    status.state = "Running"
    status.active_buildid = status.latest_buildid
    status.active_volume = update_volume
    patch.status.update(
        **status.model_dump(
            include={"state", "ready", "active_buildid", "active_volume"}, by_alias=True
        )
    )


@kopf.timer(  # type: ignore[arg-type]
    "arkcluster", interval=ARK_UPDATE_INTERVAL, initial_delay=ARK_UPDATE_INTERVAL
)
async def check_updates(**kwargs: Unpack[TimerEvent]) -> None:
    """Check for ARK server updates."""

    status = ArkClusterStatus(**kwargs["status"])
    logger = kwargs["logger"]

    if not status.ready or not status.state or not status.state.startswith("Running"):
        logger.info("Skipping update check because cluster is not ready.")
        return

    if DRY_RUN:
        latest_version = 1
    else:
        steam = Steam(Path(gettempdir()) / "steam")
        latest_version = await steam.get_latest_ark_buildid()
    kwargs["patch"].status["latestBuildid"] = latest_version
    status.latest_buildid = latest_version
    logger.info("Latest ARK version: %s", latest_version)

    active_version = status.active_buildid or 1
    if latest_version > active_version:
        logger.info("Updating cluster from %s to %s", active_version, latest_version)
        await _update_server(
            name=kwargs["name"] or DEFAULT_NAME,
            namespace=kwargs.get("namespace") or DEFAULT_NAMESPACE,
            spec=ArkClusterSpec(**kwargs["spec"]),
            logger=logger,
            status=ArkClusterStatus(**kwargs["status"]),
            patch=kwargs["patch"],
        )


@kopf.timer(  # type: ignore[arg-type]
    "arkcluster", interval=15
)
async def check_status(**kwargs: Unpack[TimerEvent]) -> None:
    """Check for ARK server updates."""

    status = ArkClusterStatus(**kwargs["status"])
    spec = ArkClusterSpec(**kwargs["spec"])
    patch = kwargs["patch"]
    logger = kwargs["logger"]

    if not status.ready and (
        status.state.startswith("Running") or status.state is None
    ):
        status.ready = True
        if status.state is None:
            status.state = "Running"
        patch.status.update(
            **status.model_dump(include={"state", "ready"}, by_alias=True)
        )

    if not status.ready or not status.state or not status.state.startswith("Running"):
        status.created_pods = 0
        status.ready_pods = 0
        status.total_pods = len(spec.server.active_maps)
        status.suspended_pods = len(spec.server.suspend)
        patch.status.update(
            **status.model_dump(
                include={
                    "ready",
                    "created_pods",
                    "ready_pods",
                    "total_pods",
                    "state",
                    "suspended_pods",
                },
                by_alias=True,
            )
        )

        logger.info("Skipping status check because cluster is not ready.")
        return

    logger = kwargs["logger"]
    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE

    try:
        created = await asyncio.gather(
            *[
                create_server_pod(
                    name=name,
                    namespace=namespace,
                    map_id=m,
                    active_volume=status.active_volume or "server-a",
                    spec=spec,
                    logger=logger,
                    dry_run=DRY_RUN,
                )
                for m in spec.server.active_maps
            ]
        )
    except Exception as ex:  # noqa: BLE001
        logger.warning("Failed to create server pods", exc_info=ex)
        return

    if any(created):
        logger.info("Created %s server pod(s)", len([x for x in created if x]))
        return

    containers = 0
    ready = 0
    total = len(spec.server.active_maps)
    for map_id in spec.server.active_maps:
        try:
            obj = await get_server_pod(name=name, namespace=namespace, map_id=map_id)
        except Exception as ex:  # noqa: BLE001
            logger.warning("Failed to get server pod", exc_info=ex)
            return

        if not obj:
            continue

        containers += 1
        if is_server_pod_ready(obj):
            ready += 1

    logger.info(
        "Status: ready: %s, running: %s, total: %s, suspeded: %s",
        ready,
        containers,
        total,
        len(spec.server.suspend),
    )
    status.ready = True
    status.created_pods = containers
    status.ready_pods = ready
    status.total_pods = total
    status.state = f"Running ({ready}/{containers}/{total})"
    status.suspended_pods = len(spec.server.suspend)

    patch.status.update(
        **status.model_dump(
            include={
                "ready",
                "created_pods",
                "ready_pods",
                "total_pods",
                "state",
                "suspended_pods",
            },
            by_alias=True,
        )
    )
