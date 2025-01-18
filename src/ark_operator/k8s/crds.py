"""ARK operator crds."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

import yaml
from aiofiles import open as aopen
from kubernetes_asyncio.client import ApiException

from ark_operator.exceptions import K8sError
from ark_operator.k8s.client import get_v1_ext_client

CRD_FILE = Path(__file__).parent.parent / "resources" / "crds.yml"
ERROR_CRDS_INSTALLED = "ArkCluster CRDs are already installed"
ERROR_CRDS_NOT_INSTALLED = "ArkCluster CRDs are not installed"


async def are_crds_installed() -> bool:
    """Check if ArkCluster CRDs are installed."""

    v1 = await get_v1_ext_client()
    try:
        await v1.read_custom_resource_definition("arkclusters.mort.is")
    except ApiException as ex:
        if ex.status == HTTPStatus.NOT_FOUND:
            return False
        raise
    return True


async def uninstall_crds() -> None:
    """Uninstall ArkCluster CRDs."""

    if not await are_crds_installed():
        raise K8sError(ERROR_CRDS_NOT_INSTALLED)

    v1 = await get_v1_ext_client()
    await v1.delete_custom_resource_definition("arkclusters.mort.is")


async def install_crds() -> None:
    """Install ArkCluster CRDs."""

    async with aopen(CRD_FILE) as f:
        crds = yaml.safe_load(await f.read())

    v1 = await get_v1_ext_client()
    if await are_crds_installed():
        await v1.patch_custom_resource_definition(body=crds)
    else:
        await v1.create_custom_resource_definition(body=crds)
