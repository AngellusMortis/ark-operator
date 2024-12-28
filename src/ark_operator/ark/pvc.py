"""ARK operator code for PVCs."""

import kopf

from ark_operator.data import ArkDataSpec, ArkServerSpec
from ark_operator.k8s import check_pvc_exists, create_pvc

MIN_SIZE_SERVER = "50Gi"

ERROR_PVC_ALREADY_EXISTS = "Failed to create PVC because it already exists."


async def update_server_pvc(
    *,
    name: str,
    namespace: str,
    spec: ArkServerSpec,
    logger: kopf.Logger,
    allow_existing: bool = True,
) -> None:
    """Create or update ARK server PVCs."""

    pvcs = [
        f"{name}-server-a",
        f"{name}-server-b",
    ]
    for pvc in pvcs:
        if not await check_pvc_exists(
            name=pvc, namespace=namespace, logger=logger, new_size=spec.size
        ):
            await create_pvc(
                name=pvc,
                namespace=namespace,
                storage_class=spec.storage_class,
                size=spec.size,
                logger=logger,
                min_size=MIN_SIZE_SERVER,
            )

            # TODO: Initial ARK server PVCs
        elif not allow_existing:
            raise kopf.PermanentError(ERROR_PVC_ALREADY_EXISTS)

        # TODO: handle additional updates from server PVC


async def update_data_pvc(
    *,
    name: str,
    namespace: str,
    spec: ArkDataSpec,
    logger: kopf.Logger,
    warn_existing: bool = False,
) -> None:
    """Create or update ARK data PVC."""

    pvc = f"{name}-data"
    if not await check_pvc_exists(
        name=pvc, namespace=namespace, logger=logger, new_size=spec.size
    ):
        await create_pvc(
            name=pvc,
            namespace=namespace,
            storage_class=spec.storage_class,
            size=spec.size,
            logger=logger,
        )

        # TODO: Initial ARK data PVC
    elif warn_existing:
        logger.warning("Failed to delete PVC because it already exists: %s", name)

    # TODO: handle additional updates from data PVC
