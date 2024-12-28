"""Main handlers for kopf."""

from typing import Unpack

import kopf

from ark_operator.ark import delete_cluster, update_cluster
from ark_operator.data import ActivityEvent, ArkClusterSpec, ChangeEvent
from ark_operator.k8s import get_k8s_client

DEFAULT_NAME = "ark"
DEFAULT_NAMESPACE = "default"


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
async def on_create(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    logger = kwargs["logger"]
    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE
    spec = ArkClusterSpec(**kwargs["spec"])

    await update_cluster(
        name=name, namespace=namespace, spec=spec, logger=logger, allow_existing=False
    )


@kopf.on.update("arkcluster")  # type: ignore[arg-type]
async def on_update(**kwargs: Unpack[ChangeEvent]) -> None:
    """Update an ARKCluster."""

    logger = kwargs["logger"]
    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE
    spec = ArkClusterSpec(**kwargs["spec"])

    await update_cluster(name=name, namespace=namespace, spec=spec, logger=logger)


@kopf.on.delete("arkcluster")  # type: ignore[arg-type]
async def on_delete(**kwargs: Unpack[ChangeEvent]) -> None:
    """Delete an ARKCluster."""

    logger = kwargs["logger"]
    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE
    spec = ArkClusterSpec(**kwargs["spec"])

    await delete_cluster(
        name=name, namespace=namespace, persist=spec.data.persist, logger=logger
    )
