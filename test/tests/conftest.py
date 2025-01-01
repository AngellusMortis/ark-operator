"""Tests conftest."""

from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest

from ark_operator.command import run_sync

BASE_DIR = Path(__file__).parent.parent.parent
CLUSTER_CRD = BASE_DIR / "crd_chart" / "crds" / "ArkCluster.yml"


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
def k8s_namespace() -> Generator[str, None, None]:
    """Create k8s namespace for testing."""

    namespace = f"kubetest-{uuid4()}"
    run_sync(f"kubectl create namespace {namespace}")

    try:
        yield namespace
    finally:
        run_sync(f"kubectl delete namespace {namespace}")


def pytest_sessionfinish() -> None:
    """On pytest session creation."""

    remove_test_namespaces()
