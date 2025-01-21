"""Delete handlers for kopf."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Unpack

import kopf

from ark_operator.ark import check_init_job, delete_secrets, delete_server_pod
from ark_operator.data import (
    ArkClusterSpec,
    ChangeEvent,
)
from ark_operator.handlers.utils import (
    DEFAULT_NAME,
    DEFAULT_NAMESPACE,
    remove_tracked_instance,
)
from ark_operator.k8s import delete_pvc

if TYPE_CHECKING:
    from collections.abc import Coroutine


@kopf.on.delete("arkcluster")  # type: ignore[arg-type]
async def on_delete_resources(**kwargs: Unpack[ChangeEvent]) -> None:
    """Delete an ARKCluster."""

    remove_tracked_instance(kwargs["name"], kwargs["namespace"])

    logger = kwargs["logger"]
    name = kwargs["name"] or DEFAULT_NAME
    namespace = kwargs.get("namespace") or DEFAULT_NAMESPACE
    spec = ArkClusterSpec(**kwargs["spec"])

    tasks: list[Coroutine[Any, Any, Any]] = [
        check_init_job(
            name=name, namespace=namespace, logger=logger, force_delete=True
        ),
    ]
    tasks.extend(
        delete_server_pod(name=name, namespace=namespace, map_id=m, logger=logger)
        for m in spec.server.all_maps
    )
    await asyncio.gather(*tasks)

    tasks = [delete_secrets(name=name, namespace=namespace, logger=logger)]
    if not spec.server.persist:
        tasks.append(
            delete_pvc(
                name=f"{name}-server-a",
                namespace=namespace,
                logger=logger,
            )
        )
        tasks.append(
            delete_pvc(
                name=f"{name}-server-b",
                namespace=namespace,
                logger=logger,
            )
        )

    if not spec.data.persist:
        tasks.append(
            delete_pvc(
                name=f"{name}-data",
                namespace=namespace,
                logger=logger,
            )
        )

    await asyncio.gather(*tasks)
