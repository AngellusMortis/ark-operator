"""Misc handlers for kopf."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from tempfile import gettempdir
from typing import TYPE_CHECKING, Unpack

import kopf

from ark_operator.ark import check_update_job, create_update_job
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
)
from ark_operator.k8s import get_k8s_client
from ark_operator.log import DEFAULT_LOG_CONFIG, init_logging
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
    await get_k8s_client()


@kopf.on.cleanup()  # type: ignore[arg-type]
async def cleanup(**_: Unpack[ActivityEvent]) -> None:
    """Kopf cleanup handler."""

    client = await get_k8s_client()
    await client.close()


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
    patch.status["state"] = status.state
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

    status.state = "Running"
    status.active_buildid = status.latest_buildid
    patch.status["activeBuildid"] = status.latest_buildid
    patch.status["state"] = status.state


@kopf.timer(  # type: ignore[arg-type]
    "arkcluster", interval=ARK_UPDATE_INTERVAL, initial_delay=ARK_UPDATE_INTERVAL
)
async def check_updates(**kwargs: Unpack[TimerEvent]) -> None:
    """Check for ARK server updates."""

    status = ArkClusterStatus(**kwargs["status"])
    logger = kwargs["logger"]

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
