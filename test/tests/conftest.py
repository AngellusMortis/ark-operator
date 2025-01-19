"""Tests conftest."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from aiofiles import tempfile

from ark_operator.command import run_sync
from ark_operator.k8s import close_k8s_client

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator


BASE_DIR = Path(__file__).parent.parent.parent
CLUSTER_CRD = BASE_DIR / "crd_chart" / "crds" / "ArkCluster.yml"
ERROR_K8S = "k8s mark required to use k8s namespace"


def remove_test_namespaces() -> None:
    """Remove all namespaces created by pytest."""

    result = run_sync(
        "kubectl get namespace --no-headers -o custom-columns=':metadata.name'"
    )
    for namespace in result.stdout.split("\n"):
        if namespace.startswith("kubetest-"):
            remove_cluster_finalizers(namespace)
            run_sync(f"kubectl delete namespace {namespace}")


def remove_cluster_finalizers(namespace: str) -> None:
    """Remove finalizers from ArkCluster objects."""

    result = run_sync(
        f"kubectl -n {namespace} get ArkCluster --no-headers -o custom-columns=':metadata.name'"
    )
    for cluster in result.stdout.split("\n"):
        run_sync(
            f'kubectl -n {namespace} patch ArkCluster {cluster} --type json --patch=\'[ {{ "op": "remove", "path": "/metadata/finalizers" }} ]\'',
        )


@pytest.fixture
def marks(request: pytest.FixtureRequest) -> list[str]:
    """Active marks for test."""

    _marks = [m.name for m in request.node.iter_markers()]
    if request.node.parent:
        _marks += [m.name for m in request.node.parent.iter_markers()]
    return _marks


@pytest.fixture
def k8s_namespace(marks: list[str]) -> Generator[str, None, None]:
    """Create k8s namespace for testing."""

    if "k8s" not in marks:
        raise RuntimeError(ERROR_K8S)

    namespace = f"kubetest-{uuid4()}"
    run_sync(f"kubectl create namespace {namespace}")
    run_sync(
        f"jinja2 {(BASE_DIR / 'test' / 'manifests' / 'rbac.yml.j2')!s} -D namespace={namespace} -D instance_name=ark | kubectl apply -f -",
        shell=True,
    )

    try:
        yield namespace
    finally:
        run_sync(
            f"jinja2 {(BASE_DIR / 'test' / 'manifests' / 'rbac.yml.j2')!s} -D namespace={namespace} -D instance_name=ark | kubectl delete -f -",
            shell=True,
        )
        run_sync(f"kubectl delete namespace {namespace}")


@pytest_asyncio.fixture(autouse=True)
async def cleanup_client() -> AsyncGenerator[None]:
    """Cleanup k8s client."""

    yield

    await close_k8s_client()


@pytest_asyncio.fixture(name="k8s_client")
async def k8s_client_fixture() -> AsyncGenerator[Mock]:
    """k8s client fixture."""

    with (
        patch("ark_operator.k8s.client.config") as mock_config,
        patch("ark_operator.k8s.client.ApiClient") as mock_klass,
    ):
        mock_config.load_kube_config = AsyncMock()

        mock_client = Mock()
        mock_client.close = AsyncMock()
        mock_klass.return_value = mock_client

        yield mock_client


@pytest_asyncio.fixture(name="k8s_v1_client")
async def k8s_v1_client_fixture(k8s_client: Mock) -> AsyncGenerator[Mock]:  # noqa: ARG001
    """k8s client fixture."""

    with (
        patch("ark_operator.k8s.client.client") as mock_v1_klass,
    ):
        mock_v1_client = Mock()
        mock_v1_client.create_namespaced_persistent_volume_claim = AsyncMock()
        mock_v1_client.delete_namespaced_persistent_volume_claim = AsyncMock()
        mock_v1_client.patch_namespaced_persistent_volume_claim = AsyncMock()
        mock_v1_client.read_namespaced_persistent_volume_claim = AsyncMock()
        mock_v1_client.read_namespaced_secret = AsyncMock()
        mock_v1_client.create_namespaced_secret = AsyncMock()
        mock_v1_client.delete_namespaced_secret = AsyncMock()
        mock_v1_client.read_namespaced_config_map = AsyncMock()
        mock_v1_client.read_namespaced_pod = AsyncMock()
        mock_v1_client.create_namespaced_pod = AsyncMock()
        mock_v1_client.patch_namespaced_pod = AsyncMock()
        mock_v1_client.delete_namespaced_pod = AsyncMock()

        mock_v1_klass.CoreV1Api.return_value = mock_v1_client

        yield mock_v1_client


@pytest_asyncio.fixture(name="k8s_v1_ext_client")
async def k8s_v1_ext_client_fixture(k8s_client: Mock) -> AsyncGenerator[Mock]:  # noqa: ARG001
    """k8s client fixture."""

    with (
        patch("ark_operator.k8s.client.client") as mock_v1_klass,
    ):
        mock_v1_client = Mock()
        mock_v1_client.read_custom_resource_definition = AsyncMock()
        mock_v1_client.delete_custom_resource_definition = AsyncMock()
        mock_v1_client.create_custom_resource_definition = AsyncMock()
        mock_v1_client.patch_custom_resource_definition = AsyncMock()

        mock_v1_klass.ApiextensionsV1Api.return_value = mock_v1_client

        yield mock_v1_client


@pytest_asyncio.fixture(name="k8s_v1_batch_client")
async def k8s_v1_batch_client_fixture(k8s_client: Mock) -> AsyncGenerator[Mock]:  # noqa: ARG001
    """k8s client fixture."""

    with (
        patch("ark_operator.k8s.client.client") as mock_v1_klass,
    ):
        mock_v1_client = Mock()
        mock_v1_client.create_namespaced_job = AsyncMock()
        mock_v1_client.read_namespaced_job = AsyncMock()
        mock_v1_client.delete_namespaced_job = AsyncMock()

        mock_v1_klass.BatchV1Api.return_value = mock_v1_client

        yield mock_v1_client


@pytest_asyncio.fixture(name="temp_dir")
async def temp_dir_fixture() -> AsyncGenerator[Path]:
    """Return temp dir for IO operations."""

    async with tempfile.TemporaryDirectory() as path:
        yield Path(path)


def pytest_sessionfinish() -> None:
    """On pytest session creation."""

    if os.environ.get("PYTEST_XDIST_WORKER") is None:
        remove_test_namespaces()
