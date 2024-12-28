"""K8s resource creators for PVCs."""

import kopf
import yaml

from ark_operator.k8s.client import get_v1_client
from ark_operator.k8s.utils import convert_k8s_size
from ark_operator.templates import loader

ERROR_PVC = "Failed to create PVC"
ERROR_PVC_TOO_SMALL = "PVC is too small. Min size is {min}"
ERROR_PVC_RESIZE_TOO_SMALL = "Failed to resize PVC, new size is smaller then old size"
ERROR_PVC_RESIZE = "Failed to resize PVC"


async def resize_pvc(
    *,
    name: str,
    namespace: str,
    new_size: int | str,
    size: int | str,
    logger: kopf.Logger,
) -> bool:
    """Resize an existing PVC."""

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
    *, name: str, namespace: str, logger: kopf.Logger, new_size: int | str | None = None
) -> bool:
    """Check if PVC exists."""

    v1 = await get_v1_client()
    try:
        pvc = await v1.read_namespaced_persistent_volume_claim(
            name=name, namespace=namespace
        )
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


async def create_pvc(  # noqa: PLR0913
    *,
    name: str,
    namespace: str,
    size: int | str,
    logger: kopf.Logger,
    access_mode: str = "ReadWriteOnce",
    storage_class: str | None = None,
    allow_exist: bool = False,
    min_size: int | str | None = None,
) -> bool:
    """Create ARK server PVC."""

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
        if allow_exist and await check_pvc_exists(
            name=name, namespace=namespace, new_size=size, logger=logger
        ):
            logger.warning(
                "Failed to delete PVC because it already exists: %s", name, exc_info=ex
            )
        else:
            raise kopf.PermanentError(ERROR_PVC) from ex
        return False

    logger.info("Created PVC: %s", obj)
    return True


async def delete_pvc(*, name: str, namespace: str, logger: kopf.Logger) -> bool:
    """Delete ARK server PVC."""

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