"""K8s resource creators for PVCs."""

import asyncio
import logging

import kopf
import yaml
from kubernetes_asyncio.client.models import V1PersistentVolumeClaim

from ark_operator.k8s.client import get_v1_client
from ark_operator.k8s.utils import convert_k8s_size
from ark_operator.templates import loader

ERROR_PVC = "Failed to create PVC"
ERROR_PVC_TOO_SMALL = "PVC is too small. Min size is {min}"
ERROR_PVC_RESIZE_TOO_SMALL = "Failed to resize PVC, new size is smaller then old size"
ERROR_PVC_RESIZE = "Failed to resize PVC"
_LOGGER = logging.getLogger(__name__)


async def resize_pvc(
    *,
    name: str,
    namespace: str,
    new_size: int | str,
    size: int | str,
    logger: kopf.Logger | None = None,
) -> bool:
    """Resize an existing PVC."""

    logger = logger or _LOGGER
    display_new_size = new_size
    display_size = size
    new_size = convert_k8s_size(new_size)
    size = convert_k8s_size(size)
    if new_size < size:
        raise kopf.PermanentError(ERROR_PVC_RESIZE_TOO_SMALL)
    if new_size == size:
        logger.info("Skipping resize for %s, sizes (%s) match", name, display_size)
        return False

    v1 = await get_v1_client()
    try:
        logger.info(
            "Resizing PVC %s from %s to %s", name, display_size, display_new_size
        )
        await v1.patch_namespaced_persistent_volume_claim(
            name=name,
            namespace=namespace,
            body={"spec": {"resources": {"requests": {"storage": display_new_size}}}},
        )
    except Exception as ex:
        raise kopf.PermanentError(ERROR_PVC_RESIZE) from ex

    return True


async def check_pvc_exists(
    *,
    name: str,
    namespace: str,
    logger: kopf.Logger | None = None,
    new_size: int | str | None = None,
) -> bool:
    """Check if PVC exists."""

    logger = logger or _LOGGER
    try:
        pvc = await get_pvc(name=name, namespace=namespace)
    except Exception:  # noqa: BLE001
        return False

    if new_size:
        await resize_pvc(
            name=name,
            namespace=namespace,
            new_size=new_size,
            size=pvc.spec.resources.requests["storage"],
            logger=logger,
        )
    return True


async def get_pvc(*, name: str, namespace: str) -> V1PersistentVolumeClaim:
    """Get PVC."""

    v1 = await get_v1_client()
    return await v1.read_namespaced_persistent_volume_claim(
        name=name, namespace=namespace
    )


async def create_pvc(  # noqa: PLR0913
    *,
    name: str,
    namespace: str,
    size: int | str,
    logger: kopf.Logger | None = None,
    access_mode: str = "ReadWriteOnce",
    storage_class: str | None = None,
    min_size: int | str | None = None,
) -> bool:
    """Create PVC."""

    logger = logger or _LOGGER
    if min_size:
        display_min_size = min_size
        min_size = convert_k8s_size(min_size)
        if convert_k8s_size(size) < min_size:
            raise kopf.PermanentError(ERROR_PVC_TOO_SMALL.format(min=display_min_size))

    pvc_tmpl = loader.get_template("pvc.yml.j2")
    pvc = yaml.safe_load(
        await pvc_tmpl.render_async(
            name=name,
            storage_class=storage_class,
            size=size,
            access_mode=access_mode,
        )
    )

    v1 = await get_v1_client()
    try:
        obj = await v1.create_namespaced_persistent_volume_claim(
            namespace=namespace,
            body=pvc,
        )
    except Exception as ex:
        raise kopf.PermanentError(ERROR_PVC) from ex

    logger.info("Waticing for PVC to be ready")
    ready = False
    while not ready:
        pvc = await get_pvc(name=name, namespace=namespace)
        if pvc.status.phase == "Bound":
            break
        await asyncio.sleep(1)

    logger.info("Created PVC: %s", obj)
    return True


async def delete_pvc(
    *, name: str, namespace: str, logger: kopf.Logger | None = None
) -> bool:
    """Delete ARK server PVC."""

    logger = logger or _LOGGER
    v1 = await get_v1_client()
    try:
        await v1.delete_namespaced_persistent_volume_claim(
            name=name, namespace=namespace
        )
    except Exception as ex:  # noqa: BLE001
        logger.warning("Failed to delete PVC: %s", name, exc_info=ex)
        return False

    logger.info("Created Steam PVC: %s", name)
    return True
