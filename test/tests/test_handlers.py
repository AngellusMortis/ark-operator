"""ARK Operator kopf tests."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Literal

import pytest
import yaml
from kopf.testing import KopfRunner

from ark_operator.command import run_sync
from ark_operator.k8s import CRD_FILE, get_v1_ext_client
from tests.conftest import remove_cluster_finalizers

if TYPE_CHECKING:
    import types
    from collections.abc import Generator
    from subprocess import CompletedProcess

    from _pytest.monkeypatch import MonkeyPatch

_LOGGER = logging.getLogger(__name__)
GHA_CANNOT_RESIZE = "Github Actions cannot resize PVCs"
CLUSTER_SPEC: dict[str, Any] = {
    "apiVersion": "mort.is/v1beta1",
    "kind": "ArkCluster",
    "metadata": {
        "name": "ark",
    },
    "spec": {
        "server": {
            "size": "2Mi",
            "maps": ["BobsMissions_WP"],
            "gracefulShutdown": 0,
        },
        "data": {"size": "2Mi"},
    },
}


class _Runner(KopfRunner):
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> Literal[False]:
        try:
            super().__exit__(exc_type, exc_val, exc_tb)
        except AttributeError as ex:
            if "'NoneType' object has no attribute 'connect'" not in str(ex):
                raise
        except RuntimeError as ex:
            if "Session is closed" not in str(ex):
                raise
        return False


@pytest.fixture(autouse=True)
def _force_pvc_mode(monkeypatch: MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("ARK_OP_FORCE_ACCESS_MODE", "ReadWriteOnce")

    yield  # noqa: PT022


def _dump_yaml(data: Any) -> str:  # noqa: ANN401
    return yaml.dump(data).replace('"', '\\"')


def _assert_output(result: CompletedProcess[str], expected: list[str]) -> None:
    items = list(filter(len, result.stdout.strip().split("\n")))
    assert sorted(items) == sorted(expected)


def _run(cmd: str, shell: bool = False, check: bool = True) -> CompletedProcess[str]:
    return run_sync(cmd, check=check, shell=shell, echo=True)


def _dump_namespace(namespace: str) -> None:
    _LOGGER.warning("Dumping namespace %s", namespace)

    _run(f"kubectl -n {namespace} get arkcluster -o yaml", check=False)
    _run(f"kubectl -n {namespace} get all", check=False)
    _run(f"kubectl -n {namespace} get pvc", check=False)

    result = _run(
        f"kubectl -n {namespace} get pvc --no-headers -o custom-columns=':metadata.name'"
    )
    for pvc in result.stdout.strip().split("\n"):
        pvc = pvc.strip()  # noqa: PLW2901
        if not pvc:
            continue

        _run(f"kubectl -n {namespace} describe pvc/{pvc}", check=False)

    result = _run(
        f"kubectl -n {namespace} get pod --no-headers -o custom-columns=':metadata.name'"
    )
    for pod in result.stdout.strip().split("\n"):
        pod = pod.strip()  # noqa: PLW2901
        if not pod:
            continue

        _run(f"kubectl -n {namespace} describe pod/{pod}", check=False)
        if "-init" in pod:
            _run(f"kubectl -n {namespace} logs -c init-perms pod/{pod}", check=False)
        if "-job" in pod:
            _run(f"kubectl -n {namespace} logs -c job pod/{pod}", check=False)
        else:
            _run(f"kubectl -n {namespace} logs pod/{pod}", check=False)


def _verify_cluster_ready(namespace: str, ready: bool = True) -> None:
    try:
        _run(
            f"kubectl -n {namespace} wait --for=jsonpath='{{.status.ready}}'={str(ready).lower()} arkcluster/ark --timeout=120s",
        )
    except Exception:
        _dump_namespace(namespace)
        raise


def _verify_startup(namespace: str) -> None:
    # PVC setup
    try:
        _run(
            f"kubectl -n {namespace} wait --for=jsonpath='{{.status.state}}'='Initializing PVCs' arkcluster/ark --timeout=60s",
        )
        result = _run(
            f"kubectl -n {namespace} get pvc --no-headers -o custom-columns=':metadata.name'"
        )
        _assert_output(result, ["ark-server-a", "ark-server-b", "ark-data"])
        _run(
            f"kubectl -n {namespace} wait --for=delete job/ark-init --timeout=300s",
        )
    except Exception:
        _dump_namespace(namespace)
        raise

    _verify_cluster_ready(namespace)

    try:
        _run(
            f"kubectl -n {namespace} wait --for=jsonpath='{{.status.phase}}'='Bound' pvc/ark-server-a --timeout=60s",
        )
        _run(
            f"kubectl -n {namespace} wait --for=jsonpath='{{.status.phase}}'='Bound' pvc/ark-server-b --timeout=60s",
        )
        _run(
            f"kubectl -n {namespace} wait --for=jsonpath='{{.status.phase}}'='Bound' pvc/ark-data --timeout=60s",
        )
        result = _run(
            f"kubectl -n {namespace} get secret --no-headers -o custom-columns=':metadata.name'"
        )
        _assert_output(result, ["ark-cluster-secrets"])
        _run(
            f"kubectl -n {namespace} wait --for=jsonpath='{{.status.readyPods}}'=1 arkcluster/ark --timeout=120s",
        )
        result = _run(
            f"kubectl -n {namespace} get service --no-headers -o custom-columns=':metadata.name'"
        )
        _assert_output(result, ["ark", "ark-rcon"])
    except Exception:
        _dump_namespace(namespace)
        raise


def _delete_cluster(
    namespace: str,
    delete_pvcs: list[str] | None = None,
    persist_pvcs: list[str] | None = None,
) -> None:
    _run(f"kubectl -n {namespace} delete ArkCluster ark")
    _run(f"kubectl -n {namespace} wait --for=delete arkcluster/ark --timeout=30s")

    delete_pvcs = delete_pvcs or ["server-a", "server-b"]
    for pvc in delete_pvcs:
        _run(f"kubectl -n {namespace} wait --for=delete pvc/ark-{pvc} --timeout=30s")

    persist_pvcs = persist_pvcs or ["data"]
    result = _run(
        f"kubectl -n {namespace} get pvc --no-headers -o custom-columns=':metadata.name'",
    )
    _assert_output(result, [f"ark-{p}" for p in persist_pvcs])

    result = _run(
        f"kubectl -n {namespace} get job --no-headers -o custom-columns=':metadata.name'",
    )
    assert result.stdout.strip() == ""


@pytest.fixture(autouse=True)
def install_crds(k8s_namespace: str) -> Generator[None, None, None]:
    """Install ArkCluster crds."""

    run_sync(f"kubectl apply -f {CRD_FILE!s}", check=False)

    yield

    remove_cluster_finalizers(k8s_namespace)


@pytest.mark.k8s
@pytest.mark.enable_socket
@pytest.mark.timeout(0)
@pytest.mark.asyncio(loop_scope="function")
async def test_crds_exist() -> None:
    """Test the CRDs are installed correctly."""

    client = await get_v1_ext_client()
    response = await client.list_custom_resource_definition(
        field_selector="metadata.name=arkclusters.mort.is"
    )

    assert len(response.items) == 1
    assert response.items[0].metadata.name == "arkclusters.mort.is"


@pytest.mark.k8s
@pytest.mark.enable_socket
@pytest.mark.timeout(0)
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
    with _Runner(args) as runner:
        pass

    assert runner.exit_code == 0
    assert runner.exception is None


@pytest.mark.k8s
@pytest.mark.enable_socket
@pytest.mark.timeout(0)
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
    with _Runner(args):
        spec = deepcopy(CLUSTER_SPEC)
        spec["spec"]["server"]["size"] = "1Ki"

        _run(
            f'echo "{_dump_yaml(spec)}" | kubectl -n {k8s_namespace} apply -f -',
            shell=True,
        )
        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.state}}'='Error: PVC is too small. Min size is 1Mi' arkcluster/ark --timeout=60s"
        )


@pytest.mark.k8s
@pytest.mark.enable_socket
@pytest.mark.timeout(0)
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
    with _Runner(args):
        spec = deepcopy(CLUSTER_SPEC)
        _run(
            f'echo "{_dump_yaml(spec)}" | kubectl -n {k8s_namespace} apply -f -',
            shell=True,
        )
        _verify_startup(k8s_namespace)
        _delete_cluster(k8s_namespace)

        _run(
            f'echo "{_dump_yaml(spec)}" | kubectl -n {k8s_namespace} apply -f -',
            shell=True,
        )
        _verify_startup(k8s_namespace)


@pytest.mark.k8s
@pytest.mark.enable_socket
@pytest.mark.timeout(0)
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
    with _Runner(args):
        spec = deepcopy(CLUSTER_SPEC)
        spec["spec"]["server"]["persist"] = True
        spec["spec"]["data"]["persist"] = False

        _run(
            f'echo "{_dump_yaml(spec)}" | kubectl -n {k8s_namespace} apply -f -',
            shell=True,
        )
        _verify_startup(k8s_namespace)
        _delete_cluster(k8s_namespace, ["data"], ["server-a", "server-b"])

        _run(
            f'echo "{_dump_yaml(spec)}" | kubectl -n {k8s_namespace} apply -f -',
            shell=True,
        )
        _verify_startup(k8s_namespace)


@pytest.mark.k8s
@pytest.mark.enable_socket
@pytest.mark.timeout(0)
@pytest.mark.xfail(reason=GHA_CANNOT_RESIZE)
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
    with _Runner(args):
        spec = deepcopy(CLUSTER_SPEC)
        _run(
            f'echo "{_dump_yaml(spec)}" | kubectl -n {k8s_namespace} apply -f -',
            shell=True,
        )
        _verify_startup(k8s_namespace)

        result = _run(
            f"kubectl -n {k8s_namespace} get pvc --no-headers -o custom-columns=':metadata.name,:spec.resources.requests.storage'"
        )
        _assert_output(
            result, ["ark-server-a   2Mi", "ark-server-b   2Mi", "ark-data       2Mi"]
        )

        spec["spec"]["server"]["size"] = "3Mi"
        spec["spec"]["data"]["size"] = "3Mi"
        _run(
            f'echo "{_dump_yaml(spec)}" | kubectl -n {k8s_namespace} apply -f -',
            shell=True,
        )
        _verify_cluster_ready(k8s_namespace, ready=False)
        _verify_cluster_ready(k8s_namespace)

        result = _run(
            f"kubectl -n {k8s_namespace} get pvc --no-headers -o custom-columns=':metadata.name,:spec.resources.requests.storage'"
        )
        _assert_output(
            result, ["ark-server-a   3Mi", "ark-server-b   3Mi", "ark-data       3Mi"]
        )


@pytest.mark.k8s
@pytest.mark.enable_socket
@pytest.mark.timeout(0)
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
    with _Runner(args):
        spec = deepcopy(CLUSTER_SPEC)
        _run(
            f'echo "{_dump_yaml(spec)}" | kubectl -n {k8s_namespace} apply -f -',
            shell=True,
        )
        _verify_startup(k8s_namespace)

        result = _run(
            f"kubectl -n {k8s_namespace} get pvc --no-headers -o custom-columns=':metadata.name,:spec.resources.requests.storage'"
        )
        _assert_output(
            result, ["ark-server-a   2Mi", "ark-server-b   2Mi", "ark-data       2Mi"]
        )

        spec["spec"]["server"]["size"] = "1Mi"
        spec["spec"]["data"]["size"] = "1Mi"
        _run(
            f'echo "{_dump_yaml(spec)}" | kubectl -n {k8s_namespace} apply -f -',
            shell=True,
        )
        _run(
            f"kubectl -n {k8s_namespace} wait --for=jsonpath='{{.status.state}}'='Error: Failed to resize PVC, new size is smaller then old size' arkcluster/ark --timeout=30s"
        )
