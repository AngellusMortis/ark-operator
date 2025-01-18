"""Delete handlers for kopf."""

import asyncio
from typing import Unpack

import kopf

from ark_operator.ark import (
    check_init_job,
)
from ark_operator.data import (
    ArkClusterSpec,
    ChangeEvent,
)
from ark_operator.handlers.update import (
    DEFAULT_NAME,
    DEFAULT_NAMESPACE,
)
from ark_operator.k8s import delete_pvc


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
        # TODO: delete servers
    )
