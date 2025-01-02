"""ARK Operator kopf tests."""

from collections.abc import Generator
from copy import deepcopy
from subprocess import CompletedProcess
from typing import Any

import pytest
import yaml
from kopf.testing import KopfRunner

from ark_operator.command import run_sync
from ark_operator.k8s import get_v1_ext_client
from tests.conftest import BASE_DIR, remove_cluster_finalizers

GHA_FAIL = "Will fail in Github Actions until pods are created"

CRDS = BASE_DIR / "crd_chart" / "crds" / "crds.yml"
CLUSTER_SPEC: dict[str, Any] = {
    "apiVersion": "mort.is/v1beta1",
    "kind": "ArkCluster",
    "metadata": {
        "name": "ark",
    },
    "spec": {
        "server": {
            "size": "2Mi",
        },
        "data": {"size": "2Mi"},
    },
}


def _assert_output(result: CompletedProcess[str], expected: list[str]) -> None:
    items = list(filter(len, result.stdout.strip().split("\n")))
    assert sorted(items) == sorted(expected)


def _run(cmd: str, shell: bool = False, check: bool = True) -> CompletedProcess[str]:
    return run_sync(cmd, check=check, shell=shell, echo=True)


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


def test_handler_startup(k8s_namespace: str) -> None:
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


def test_handler_too_small(k8s_namespace: str) -> None:
    """Test kopf Webhook."""

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
        spec = deepcopy(CLUSTER_SPEC)
        spec["spec"]["server"]["size"] = "1Ki"

        _run(
            f'echo "{yaml.dump(spec)}" | kubectl -n {k8s_namespace} apply -f -',
            shell=True,
        )
        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.state}}'='Error: PVC is too small. Min size is 1Mi' arkcluster/ark --timeout=30s"
        )

    assert runner.exit_code == 0
    assert runner.exception is None


def test_handler_basic_cluster(k8s_namespace: str) -> None:
    """Test kopf creates/updates/deletes a basic cluster."""

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
        spec = deepcopy(CLUSTER_SPEC)
        _run(
            f'echo "{yaml.dump(spec)}" | kubectl -n {k8s_namespace} apply -f -',
            shell=True,
        )
        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.ready}}'=true arkcluster/ark --timeout=30s",
        )

        result = _run(
            f"kubectl -n {k8s_namespace} get pvc --no-headers -o custom-columns=':metadata.name'"
        )
        _assert_output(result, ["ark-server-a", "ark-server-b", "ark-data"])

        _run(f"kubectl -n {k8s_namespace} delete ArkCluster ark")
        _run(
            f"kubectl -n {k8s_namespace} wait --for=delete arkcluster/ark --timeout=30s"
        )

        result = _run(
            f"kubectl -n {k8s_namespace} get pvc --no-headers -o custom-columns=':metadata.name'",
        )
        _assert_output(result, ["ark-data"])

        _run(
            f'echo "{yaml.dump(spec)}" | kubectl -n {k8s_namespace} apply -f -',
            shell=True,
        )
        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.ready}}'=true arkcluster/ark --timeout=30s",
        )
        result = _run(
            f"kubectl -n {k8s_namespace} get pvc --no-headers -o custom-columns=':metadata.name'"
        )
        _assert_output(result, ["ark-server-a", "ark-server-b", "ark-data"])

    assert runner.exit_code == 0
    assert runner.exception is None


def test_handler_server_persist(k8s_namespace: str) -> None:
    """Test kopf creates/updates/deletes a with existing PVCs cluster."""

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
        spec = deepcopy(CLUSTER_SPEC)
        spec["spec"]["server"]["persist"] = True
        spec["spec"]["data"]["persist"] = False

        _run(
            f'echo "{yaml.dump(spec)}" | kubectl -n {k8s_namespace} apply -f -',
            shell=True,
        )
        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.ready}}'=true arkcluster/ark --timeout=30s",
        )

        result = _run(
            f"kubectl -n {k8s_namespace} get pvc --no-headers -o custom-columns=':metadata.name'"
        )
        _assert_output(result, ["ark-server-a", "ark-server-b", "ark-data"])

        _run(f"kubectl -n {k8s_namespace} delete ArkCluster ark")
        _run(
            f"kubectl -n {k8s_namespace} wait --for=delete arkcluster/ark --timeout=30s"
        )

        result = _run(
            f"kubectl -n {k8s_namespace} get pvc --no-headers -o custom-columns=':metadata.name'",
        )
        _assert_output(result, ["ark-server-a", "ark-server-b"])

        _run(
            f'echo "{yaml.dump(spec)}" | kubectl -n {k8s_namespace} apply -f -',
            shell=True,
        )
        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.ready}}'=true arkcluster/ark --timeout=30s",
        )
        result = _run(
            f"kubectl -n {k8s_namespace} get pvc --no-headers -o custom-columns=':metadata.name'"
        )
        _assert_output(result, ["ark-server-a", "ark-server-b", "ark-data"])

    assert runner.exit_code == 0
    assert runner.exception is None


@pytest.mark.xfail(reason=GHA_FAIL)
def test_handler_resize_pvcs(k8s_namespace: str) -> None:
    """Test kopf creates/updates/deletes a with existing PVCs cluster."""

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
        spec = deepcopy(CLUSTER_SPEC)
        _run(
            f'echo "{yaml.dump(spec)}" | kubectl -n {k8s_namespace} apply -f -',
            shell=True,
        )
        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.ready}}'=true arkcluster/ark --timeout=30s",
        )

        result = _run(
            f"kubectl -n {k8s_namespace} get pvc --no-headers -o custom-columns=':metadata.name,:spec.resources.requests.storage'"
        )
        _assert_output(
            result, ["ark-server-a   2Mi", "ark-server-b   2Mi", "ark-data       2Mi"]
        )

        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.ready}}'=true arkcluster/ark --timeout=30s",
        )
        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.ready}}'=true arkcluster/ark --timeout=30s",
        )
        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.phase}}'='Bound' pvc/ark-server-a --timeout=30s",
        )
        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.phase}}'='Bound' pvc/ark-server-b --timeout=30s",
        )
        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.phase}}'='Bound' pvc/ark-data --timeout=30s",
        )

        spec["spec"]["server"]["size"] = "3Mi"
        spec["spec"]["data"]["size"] = "3Mi"
        _run(
            f'echo "{yaml.dump(spec)}" | kubectl -n {k8s_namespace} apply -f -',
            shell=True,
        )
        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.ready}}'=false arkcluster/ark --timeout=30s",
        )
        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.ready}}'=true arkcluster/ark --timeout=30s",
        )

        result = _run(
            f"kubectl -n {k8s_namespace} get pvc --no-headers -o custom-columns=':metadata.name,:spec.resources.requests.storage'"
        )
        _assert_output(
            result, ["ark-server-a   3Mi", "ark-server-b   3Mi", "ark-data       3Mi"]
        )

    assert runner.exit_code == 0
    assert runner.exception is None


@pytest.mark.xfail(reason=GHA_FAIL)
def test_handler_resize_pvcs_too_small(k8s_namespace: str) -> None:
    """Test kopf creates/updates/deletes a with existing PVCs cluster."""

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
        spec = deepcopy(CLUSTER_SPEC)
        _run(
            f'echo "{yaml.dump(spec)}" | kubectl -n {k8s_namespace} apply -f -',
            shell=True,
        )
        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.ready}}'=true arkcluster/ark --timeout=30s",
        )

        result = _run(
            f"kubectl -n {k8s_namespace} get pvc --no-headers -o custom-columns=':metadata.name,:spec.resources.requests.storage'"
        )
        _assert_output(
            result, ["ark-server-a   2Mi", "ark-server-b   2Mi", "ark-data       2Mi"]
        )

        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.phase}}'='Bound' pvc/ark-server-a --timeout=30s",
        )
        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.phase}}'='Bound' pvc/ark-server-b --timeout=30s",
        )
        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.phase}}'='Bound' pvc/ark-data --timeout=30s",
        )

        spec["spec"]["server"]["size"] = "1Mi"
        spec["spec"]["data"]["size"] = "1Mi"
        _run(
            f'echo "{yaml.dump(spec)}" | kubectl -n {k8s_namespace} apply -f -',
            shell=True,
        )
        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.state}}'='Error: Failed to resize PVC, new size is smaller then old size' arkcluster/ark --timeout=30s"
        )

    assert runner.exit_code == 0
    assert runner.exception is None
