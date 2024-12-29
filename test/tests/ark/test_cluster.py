"""Test ARK Cluster."""

import asyncio
from collections.abc import Generator
from unittest.mock import patch

import kopf
import pytest
import pytest_asyncio

from ark_operator.ark import update_cluster, update_data_pvc
from ark_operator.data import ArkClusterSpec
from ark_operator.k8s import check_pvc_exists, get_pvc

TEST_SPEC = ArkClusterSpec(
    server={  # type: ignore[arg-type]
        "size": "10Mi",
        "maps": ["BobsMissions_WP"],
    },
    data={  # type: ignore[arg-type]
        "size": "10Mi",
        "persist": True,
    },
)


@pytest.fixture(autouse=True)
def _min_size() -> Generator[None, None, None]:
    with patch("ark_operator.ark.pvc.MIN_SIZE_SERVER", "1Ki"):
        yield


@pytest_asyncio.fixture(scope="function")
async def _ark_cluster(k8s_namespace: str) -> None:
    await update_cluster(
        name="ark",
        namespace=k8s_namespace,
        spec=TEST_SPEC.model_copy(),
        allow_existing=False,
    )


@pytest_asyncio.fixture(scope="function")
async def _ark_data_pvc(k8s_namespace: str) -> None:
    await update_data_pvc(
        name="ark",
        namespace=k8s_namespace,
        spec=TEST_SPEC.data.model_copy(),
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_update_cluster_create(k8s_namespace: str) -> None:
    """Test update_cluster creates cluster correctly."""

    spec = TEST_SPEC.model_copy()

    assert await check_pvc_exists(name="ark-server-a", namespace=k8s_namespace) is False
    assert await check_pvc_exists(name="ark-server-b", namespace=k8s_namespace) is False
    assert await check_pvc_exists(name="ark-data", namespace=k8s_namespace) is False

    await update_cluster(
        name="ark",
        namespace=k8s_namespace,
        spec=spec,
        allow_existing=False,
    )

    pvc = await get_pvc(name="ark-server-a", namespace=k8s_namespace)
    assert pvc.spec.access_modes == ["ReadWriteOnce"]
    assert pvc.spec.resources.requests == {"storage": "10Mi"}

    pvc = await get_pvc(name="ark-server-b", namespace=k8s_namespace)
    assert pvc.spec.access_modes == ["ReadWriteOnce"]
    assert pvc.spec.resources.requests == {"storage": "10Mi"}

    pvc = await get_pvc(name="ark-data", namespace=k8s_namespace)
    assert pvc.spec.access_modes == ["ReadWriteMany"]
    assert pvc.spec.resources.requests == {"storage": "10Mi"}


@pytest.mark.usefixtures("_ark_cluster")
@pytest.mark.asyncio(loop_scope="session")
async def test_update_cluster_with_existing_cluster(k8s_namespace: str) -> None:
    """Test allow_existing on update_cluster."""

    spec = TEST_SPEC.model_copy()
    spec.server.size = "20Mi"

    with pytest.raises(kopf.PermanentError):
        await update_cluster(
            name="ark",
            namespace=k8s_namespace,
            spec=spec,
            allow_existing=False,
        )

    pvc = await get_pvc(name="ark-server-a", namespace=k8s_namespace)
    assert pvc.spec.access_modes == ["ReadWriteOnce"]
    assert pvc.spec.resources.requests == {"storage": "10Mi"}

    pvc = await get_pvc(name="ark-server-b", namespace=k8s_namespace)
    assert pvc.spec.access_modes == ["ReadWriteOnce"]
    assert pvc.spec.resources.requests == {"storage": "10Mi"}


@pytest.mark.usefixtures("_ark_data_pvc")
@pytest.mark.asyncio(loop_scope="session")
async def test_update_cluster_create_with_data(k8s_namespace: str) -> None:
    """Test update_cluster creates cluster even if there is an data PVC."""

    spec = TEST_SPEC.model_copy()
    spec.server.size = "20Mi"
    spec.data.size = "22Mi"

    await update_cluster(
        name="ark",
        namespace=k8s_namespace,
        spec=spec,
        allow_existing=False,
    )

    pvc = await get_pvc(name="ark-server-a", namespace=k8s_namespace)
    assert pvc.spec.access_modes == ["ReadWriteOnce"]
    assert pvc.spec.resources.requests == {"storage": "20Mi"}

    pvc = await get_pvc(name="ark-server-b", namespace=k8s_namespace)
    assert pvc.spec.access_modes == ["ReadWriteOnce"]
    assert pvc.spec.resources.requests == {"storage": "20Mi"}

    pvc = await get_pvc(name="ark-data", namespace=k8s_namespace)
    assert pvc.spec.access_modes == ["ReadWriteMany"]
    assert pvc.spec.resources.requests == {"storage": "22Mi"}


@pytest.mark.usefixtures("_ark_cluster")
@pytest.mark.asyncio(loop_scope="session")
async def test_update_cluster_update(k8s_namespace: str) -> None:
    """Test update_cluster updates cluster."""

    spec = TEST_SPEC.model_copy()
    spec.server.size = "20Mi"
    spec.data.size = "22Mi"

    await asyncio.sleep(5)

    await update_cluster(name="ark", namespace=k8s_namespace, spec=spec)

    pvc = await get_pvc(name="ark-server-a", namespace=k8s_namespace)
    assert pvc.spec.access_modes == ["ReadWriteOnce"]
    assert pvc.spec.resources.requests == {"storage": "20Mi"}

    pvc = await get_pvc(name="ark-server-b", namespace=k8s_namespace)
    assert pvc.spec.access_modes == ["ReadWriteOnce"]
    assert pvc.spec.resources.requests == {"storage": "20Mi"}

    pvc = await get_pvc(name="ark-data", namespace=k8s_namespace)
    assert pvc.spec.access_modes == ["ReadWriteMany"]
    assert pvc.spec.resources.requests == {"storage": "22Mi"}
