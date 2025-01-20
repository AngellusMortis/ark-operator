"""ARK operator crds."""

from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path

import yaml
from aiofiles import open as aopen
from kubernetes_asyncio.client import ApiException

from ark_operator.command import run_async
from ark_operator.data import ArkClusterSpec
from ark_operator.exceptions import K8sError
from ark_operator.k8s.client import get_crd_client, get_v1_ext_client

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


async def get_cluster(
    *, name: str, namespace: str, version: str = "v1beta1"
) -> ArkClusterSpec:
    """Get ArkCluster."""

    v1 = await get_crd_client()
    data = await v1.get_namespaced_custom_object(
        group="mort.is",
        plural="arkclusters",
        version=version,
        name=name,
        namespace=namespace,
    )
    return ArkClusterSpec(**data["spec"])


async def update_cluster(*, name: str, namespace: str, spec: ArkClusterSpec) -> None:
    """Update ArkCluster."""

    data = spec.model_dump(mode="json", by_alias=True)
    if "loadBalancerIp" in data["server"]:
        data["server"]["loadBalancerIP"] = data["server"].pop("loadBalancerIp")
    if "multihomeIp" in data["globalSettings"]:
        data["globalSettings"]["multihomeIP"] = data["globalSettings"].pop(
            "multihomeIp"
        )
    if "clusterId" in data["globalSettings"]:
        data["globalSettings"]["clusterID"] = data["globalSettings"].pop("clusterId")
    del data["server"]["allMaps"]
    del data["server"]["allServers"]

    await run_async(  # noqa: S604
        f"echo '{json.dumps({'spec': data})}' | kubectl -n {namespace} patch arkcluster {name} --type merge --patch-file=/dev/stdin",  # noqa: E501
        shell=True,
    )
