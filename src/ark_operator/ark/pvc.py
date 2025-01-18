"""ARK operator code for PVCs."""

import asyncio
import logging

import kopf
from environs import Env

from ark_operator.data import ArkDataSpec, ArkServerSpec
from ark_operator.k8s import (
    check_pvc_exists,
    create_pvc,
)

_ENV = Env()
MIN_SIZE_SERVER = _ENV("ARK_OP_MIN_SERVER_SIZE", "50Gi")
_LOGGER = logging.getLogger(__name__)


async def update_server_pvc(
    *,
    name: str,
    namespace: str,
    spec: ArkServerSpec,
    logger: kopf.Logger | None = None,
) -> None:
    """Create or update ARK server PVCs."""

    logger = logger or _LOGGER
    tasks = []
    for pvc_name in ["server-a", "server-b"]:
        if not await check_pvc_exists(
            name=f"{name}-{pvc_name}",
            namespace=namespace,
            logger=logger,
            new_size=spec.size,
        ):
            tasks.append(  # noqa: PERF401
                create_pvc(
                    name=pvc_name,
                    instance_name=name,
                    namespace=namespace,
                    storage_class=spec.storage_class,
                    access_mode="ReadWriteMany",
                    size=spec.size,
                    logger=logger,
                    min_size=MIN_SIZE_SERVER,
                )
            )

    if tasks:
        await asyncio.gather(*tasks)


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
    full_name = f"{name}-data"
    if not await check_pvc_exists(
        name=full_name, namespace=namespace, logger=logger, new_size=spec.size
    ):
        await create_pvc(
            name="data",
            instance_name=name,
            namespace=namespace,
            storage_class=spec.storage_class,
            access_mode="ReadWriteMany",
            size=spec.size,
            logger=logger,
        )
    elif warn_existing:
        logger.warning("Failed to create PVC because it already exists: %s", name)
