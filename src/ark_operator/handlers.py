"""Main handlers for kopf."""

from typing import Unpack

import kopf

from ark_operator.data import ActivityEvent, ArkClusterSpec, ChangeEvent
from ark_operator.k8s import create_pvc, delete_pvc, get_k8s_client, resize_pvc

MIN_SIZE_SERVER = "50Gi"


@kopf.on.startup()  # type: ignore[arg-type]
async def startup(**_: Unpack[ActivityEvent]) -> None:
    """Kopf startup handler."""

    await get_k8s_client()


@kopf.on.cleanup()  # type: ignore[arg-type]
async def cleanup(**_: Unpack[ActivityEvent]) -> None:
    """Kopf cleanup handler."""

    client = await get_k8s_client()
    await client.close()


@kopf.on.create("arkcluster")  # type: ignore[arg-type]
async def on_create(**kwargs: Unpack[ChangeEvent]) -> None:
    """Create an ARKCluster."""

    logger = kwargs["logger"]

    name = kwargs.get("name")
    namespace = kwargs.get("namespace") or "default"
    spec = ArkClusterSpec(**kwargs["spec"])

    await create_pvc(
        name=f"{name}-server-a",
        namespace=namespace,
        storage_class=spec.server.storage_class,
        size=spec.server.size,
        logger=logger,
        min_size=MIN_SIZE_SERVER,
    )
    await create_pvc(
        name=f"{name}-server-b",
        namespace=namespace,
        storage_class=spec.server.storage_class,
        size=spec.server.size,
        logger=logger,
        min_size=MIN_SIZE_SERVER,
    )
    await create_pvc(
        name=f"{name}-data",
        namespace=namespace,
        storage_class=spec.data.storage_class,
        size=spec.data.size,
        logger=logger,
        allow_exist=True,
    )

    # Initial ARK server PVCs
    # Initial ARK data PVC
    # Create ConfigMap per server
    # Create pod for each server


@kopf.on.update("arkcluster")  # type: ignore[arg-type]
async def on_update(**kwargs: Unpack[ChangeEvent]) -> None:
    """Update an ARKCluster."""

    logger = kwargs["logger"]
    name = kwargs.get("name")
    namespace = kwargs.get("namespace") or "default"
    spec = ArkClusterSpec(**kwargs["spec"])

    old = kwargs.get("old") or {}
    old_spec = ArkClusterSpec(**old.get("spec", {}))

    if await resize_pvc(
        name=f"{name}-server-a",
        namespace=namespace,
        new_size=spec.server.size,
        size=old_spec.server.size,
        logger=logger,
    ):
        # TODO: decide how to handle resizing PVCs with servers
        pass

    if await resize_pvc(
        name=f"{name}-server-b",
        namespace=namespace,
        new_size=spec.server.size,
        size=old_spec.server.size,
        logger=logger,
    ):
        # TODO: decide how to handle resizing PVCs with servers
        pass

    if await resize_pvc(
        name=f"{name}-data",
        namespace=namespace,
        new_size=spec.data.size,
        size=old_spec.data.size,
        logger=logger,
    ):
        # TODO: decide how to handle resizing PVCs with servers
        pass

    # Check for updates to ConfigMaps -> restart servers
    # Check for new/removed servers and update pods


@kopf.on.delete("arkcluster")  # type: ignore[arg-type]
async def on_delete(**kwargs: Unpack[ChangeEvent]) -> None:
    """Delete an ARKCluster."""

    logger = kwargs["logger"]

    name = kwargs.get("name")
    namespace = kwargs.get("namespace") or "default"
    spec = ArkClusterSpec(**kwargs["spec"])

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
    if not spec.data.persist:
        await delete_pvc(
            name=f"{name}-data",
            namespace=namespace,
            logger=logger,
        )

    # Clean up ConfigMaps
    # Clean up pods
