"""ARK operator code for PVCs."""

import asyncio
import logging

import kopf

from ark_operator.data import ArkDataSpec, ArkServerSpec
from ark_operator.k8s import check_pvc_exists, create_pvc

MIN_SIZE_SERVER = "50Gi"

ERROR_PVC_ALREADY_EXISTS = "Failed to create PVC because it already exists."
_LOGGER = logging.getLogger(__name__)


async def update_server_pvc(
    *,
    name: str,
    namespace: str,
    spec: ArkServerSpec,
    logger: kopf.Logger | None = None,
    allow_existing: bool = True,
) -> None:
    """Create or update ARK server PVCs."""

    logger = logger or _LOGGER
    pvcs = [
        f"{name}-server-a",
        f"{name}-server-b",
    ]
    tasks = []
    new_size = spec.size if allow_existing else None
    for pvc_name in pvcs:
        if not await check_pvc_exists(
            name=pvc_name, namespace=namespace, logger=logger, new_size=new_size
        ):
            tasks.append(
                create_pvc(
                    name=pvc_name,
                    namespace=namespace,
                    storage_class=spec.storage_class,
                    size=spec.size,
                    logger=logger,
                    min_size=MIN_SIZE_SERVER,
                )
            )

            # TODO: Initial ARK server PVCs
        elif not allow_existing:
            raise kopf.PermanentError(ERROR_PVC_ALREADY_EXISTS)

    if tasks:
        await asyncio.gather(*tasks)

        # TODO: handle additional updates from server PVC


async def update_data_pvc(
    *,
    name: str,
    namespace: str,
    spec: ArkDataSpec,
    logger: kopf.Logger | None = None,
    warn_existing: bool = False,
) -> None:
    """Create or update ARK data PVC."""

    logger = logger or _LOGGER
    pvc = f"{name}-data"
    if not await check_pvc_exists(
        name=pvc, namespace=namespace, logger=logger, new_size=spec.size
    ):
        await create_pvc(
            name=pvc,
            namespace=namespace,
            storage_class=spec.storage_class,
            access_mode="ReadWriteMany",
            size=spec.size,
            logger=logger,
        )

        # TODO: Initial ARK data PVC
    elif warn_existing:
        logger.warning("Failed to delete PVC because it already exists: %s", name)

    # TODO: handle additional updates from data PVC
