"""Main handlers for kopf."""

import kopf

from ark_operator.data import ActivityEvent, ArkClusterSpec, ChangeEvent
from ark_operator.k8s import create_pvc, delete_pvc, get_k8s_client, resize_pvc

try:
    from typing import Unpack  # type: ignore[attr-defined]
except ImportError:
    from typing_extensions import Unpack


DEFAULT_SERVER_SIZE = "50Gi"
DEFAULT_DATA_SIZE = "50Gi"
DEFAULT_DATA_PERSIST = True
MIN_SIZE_SERVER = "50Gi"


@kopf.on.startup()
async def startup(**_: Unpack[ActivityEvent]) -> None:
    """Kopf startup handler."""

    await get_k8s_client()


@kopf.on.cleanup()
async def cleanup(**_: Unpack[ActivityEvent]) -> None:
    """Kopf cleanup handler."""

    client = await get_k8s_client()
    await client.close()


@kopf.on.create("arkcluster")
async def on_create(**kwargs: Unpack[ChangeEvent[ArkClusterSpec]]) -> None:
    """Create an ARKCluster."""

    logger = kwargs.pop("logger")

    name = kwargs.pop("name")
    namespace = kwargs.pop("namespace")
    spec = kwargs.pop("spec")
    server = spec.get("server", {})
    data = spec.get("data", {})

    await create_pvc(
        cluster_name=name,
        pvc_name="server-a",
        namespace=namespace,
        storage_class=server.get("storageClass"),
        size=server.get("size", DEFAULT_SERVER_SIZE),
        logger=logger,
        min_size=MIN_SIZE_SERVER,
    )
    await create_pvc(
        cluster_name=name,
        pvc_name="server-b",
        namespace=namespace,
        storage_class=server.get("storageClass"),
        size=server.get("size", DEFAULT_SERVER_SIZE),
        logger=logger,
        min_size=MIN_SIZE_SERVER,
    )
    await create_pvc(
        cluster_name=name,
        pvc_name="data",
        namespace=namespace,
        storage_class=data.get("storageClass"),
        size=data.get("size", DEFAULT_DATA_SIZE),
        logger=logger,
        allow_exist=True,
    )

    # Initial ARK server PVCs
    # Initial ARK data PVC
    # Create ConfigMap per server
    # Create pod for each server


@kopf.on.update("arkcluster")
async def on_update(**kwargs: Unpack[ChangeEvent[ArkClusterSpec]]) -> None:
    """Update an ARKCluster."""

    logger = kwargs.pop("logger")
    name = kwargs.pop("name")
    namespace = kwargs.pop("namespace")
    spec: ArkClusterSpec = kwargs.pop("spec")
    server = spec.get("server", {})
    size = server.get("size", DEFAULT_SERVER_SIZE)

    old = kwargs.pop("old", {})
    old_spec = old.get("spec", {})
    old_server = old_spec.get("server", {})
    old_size = old_server.get("size", DEFAULT_SERVER_SIZE)

    if await resize_pvc(
        name=f"{name}-server-a",
        namespace=namespace,
        new_size=size,
        size=old_size,
        logger=logger,
    ):
        # TODO: decide how to handle resizing PVCs with servers
        pass

    if await resize_pvc(
        name=f"{name}-server-b",
        namespace=namespace,
        new_size=size,
        size=old_size,
        logger=logger,
    ):
        # TODO: decide how to handle resizing PVCs with servers
        pass

    data = spec.get("data", {})
    size = data.get("size", DEFAULT_DATA_SIZE)

    old_data = old.get("data", {})
    old_size = old_data.get("size", DEFAULT_DATA_SIZE)

    if await resize_pvc(
        name=f"{name}-data",
        namespace=namespace,
        new_size=size,
        size=old_size,
        logger=logger,
    ):
        # TODO: decide how to handle resizing PVCs with servers
        pass

    # Check for updates to ConfigMaps -> restart servers
    # Check for new/removed servers and update pods


@kopf.on.delete("arkcluster")
async def on_delete(**kwargs: Unpack[ChangeEvent[ArkClusterSpec]]) -> None:
    """Delete an ARKCluster."""

    logger = kwargs.pop("logger")

    name = kwargs.pop("name")
    namespace = kwargs.pop("namespace")
    spec = kwargs.pop("spec")
    data = spec.get("data", {})

    await delete_pvc(
        cluster_name=name,
        pvc_name="server-a",
        namespace=namespace,
        logger=logger,
    )
    await delete_pvc(
        cluster_name=name,
        pvc_name="server-b",
        namespace=namespace,
        logger=logger,
    )
    if not data.get("persist", DEFAULT_DATA_PERSIST):
        await delete_pvc(
            cluster_name=name,
            pvc_name="data",
            namespace=namespace,
            logger=logger,
        )

    # Clean up ConfigMaps
    # Clean up pods
