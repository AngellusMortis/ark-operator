"""ARK operator code for PVCs."""

import kopf

from ark_operator.ark.pvc import update_data_pvc, update_server_pvc
from ark_operator.data import ArkClusterSpec
from ark_operator.k8s import delete_pvc


async def update_cluster(
    *,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
    logger: kopf.Logger,
    allow_existing: bool = True,
) -> None:
    """Update ARK Cluster."""

    await update_server_pvc(
        name=name,
        namespace=namespace,
        spec=spec.server,
        logger=logger,
        allow_existing=allow_existing,
    )
    await update_data_pvc(
        name=name,
        namespace=namespace,
        spec=spec.data,
        logger=logger,
        warn_existing=not allow_existing,
    )

    # TODO: Create ConfigMap per server
    # TODO: Create pod for each server


async def delete_cluster(
    *, name: str, namespace: str, persist: bool, logger: kopf.Logger
) -> None:
    """Delete ARK cluster."""

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
    if not persist:
        await delete_pvc(
            name=f"{name}-data",
            namespace=namespace,
            logger=logger,
        )

    # TODO: Clean up ConfigMaps
    # TODO: Clean up pods
