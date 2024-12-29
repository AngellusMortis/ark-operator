"""Tests conftest."""

from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import uuid4

import pytest_asyncio

from ark_operator.k8s import get_v1_client

BASE_DIR = Path(__file__).parent.parent.parent
CLUSTER_CRD = BASE_DIR / "crd_chart" / "crds" / "ArkCluster.yml"


@pytest_asyncio.fixture(scope="function", loop_scope="session")
async def k8s_namespace() -> AsyncGenerator[str]:
    """Create k8s namespace for testing."""

    namespace = f"kubetest-{uuid4()}"
    v1 = await get_v1_client()
    await v1.create_namespace(body={"metadata": {"name": namespace}})

    yield namespace

    await v1.delete_namespace(namespace)
