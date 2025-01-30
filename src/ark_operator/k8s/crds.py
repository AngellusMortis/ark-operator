"""ARK operator crds."""

from __future__ import annotations

import json
import logging
from http import HTTPStatus
from pathlib import Path
from typing import Any

import yaml
from aiofiles import open as aopen
from kubernetes_asyncio.client import ApiException

from ark_operator.command import run_async
from ark_operator.data import ArkClusterSpec, ArkClusterStatus
from ark_operator.exceptions import K8sError
from ark_operator.k8s.client import get_crd_client, get_v1_ext_client
from ark_operator.utils import utc_now

CRD_FILE = Path(__file__).parent.parent / "resources" / "crds.yml"
ERROR_CRDS_INSTALLED = "ArkCluster CRDs are already installed"
ERROR_CRDS_NOT_INSTALLED = "ArkCluster CRDs are not installed"
_LOGGER = logging.getLogger(__name__)


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


async def get_cluster(
    *, name: str, namespace: str, version: str = "v1beta1"
) -> tuple[ArkClusterSpec, ArkClusterStatus]:
    """Get ArkCluster."""

    v1 = await get_crd_client()
    data = await v1.get_namespaced_custom_object(
        group="mort.is",
        plural="arkclusters",
        version=version,
        name=name,
        namespace=namespace,
    )
    return ArkClusterSpec(**data["spec"]), ArkClusterStatus(**data.get("status", {}))


async def update_cluster(
    *,
    name: str,
    namespace: str,
    spec: dict[str, Any] | None = None,
    status: ArkClusterStatus | dict[str, Any] | None = None,
) -> None:
    """Update ArkCluster."""

    if not spec and not status:
        _LOGGER.debug("Skipping update because no spec or status")
        return

    data: dict[str, Any] = {}
    if spec:
        _LOGGER.debug("Updating spec: %s", spec)
        data["spec"] = spec

    if status:
        if isinstance(status, ArkClusterStatus):
            status = status.model_dump(mode="json")
        _LOGGER.debug("Updating status: %s", status)
        data["status"] = status
        data["status"]["lastUpdate"] = utc_now().isoformat()

    await run_async(  # noqa: S604
        f"echo '{json.dumps(data)}' | kubectl -n {namespace} patch arkcluster {name} --type merge --patch-file=/dev/stdin",  # noqa: E501
        shell=True,
        check=True,
        output_level=logging.INFO,
    )
