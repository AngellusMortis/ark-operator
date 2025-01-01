"""ARK Operator kopf tests."""

from collections.abc import Generator

import pytest
from kopf.testing import KopfRunner

from ark_operator.command import run_sync
from ark_operator.k8s import get_v1_ext_client
from tests.conftest import BASE_DIR, remove_cluster_finalizers

CRDS = BASE_DIR / "crd_chart" / "crds" / "crds.yml"
CLUSTER_SPEC = {
    "apiVersion": "mort.is/v1beta1",
    "kind": "ArkCluster",
    "metadata": {
        "name": "ark",
    },
    "spec": {
        "server": {
            "size": "1Mi",
        },
        "data": {"size": "1Mi"},
    },
}


@pytest.fixture(autouse=True)
def install_crds(k8s_namespace: str) -> Generator[None, None, None]:
    """Install ArkCluster crds."""

    run_sync(f"kubectl apply -f {CRDS!s}", check=False)

    yield

    remove_cluster_finalizers(k8s_namespace)


@pytest.mark.asyncio(loop_scope="function")
async def test_crds_exist() -> None:
    """Test the CRDs are installed correctly."""

    client = await get_v1_ext_client()
    response = await client.list_custom_resource_definition(
        field_selector="metadata.name=arkclusters.mort.is"
    )

    assert len(response.items) == 1
    assert response.items[0].metadata.name == "arkclusters.mort.is"


@pytest.mark.asyncio(loop_scope="function")
async def test_handler_startup(k8s_namespace: str) -> None:
    """Test kopf starts up and shutdowns correctly."""

    args = [
        "run",
        "-n",
        k8s_namespace,
        "--verbose",
        "--standalone",
        "-m",
        "ark_operator.handlers",
    ]
    with KopfRunner(args) as runner:
        pass

    assert runner.exit_code == 0
    assert runner.exception is None
