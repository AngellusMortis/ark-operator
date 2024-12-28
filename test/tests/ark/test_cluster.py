"""Test ARK Cluster."""

from collections.abc import Generator
from unittest.mock import Mock, patch

import pytest
from kubetest.client import TestClient

from ark_operator.ark import update_cluster
from ark_operator.data import ArkClusterSpec
from ark_operator.k8s import check_pvc_exists

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


@pytest.mark.asyncio
async def test_create_cluster(kube: TestClient) -> None:
    """Test CRDs apply cleanly"""

    namespace = kube.namespace
    spec = TEST_SPEC.copy()

    assert (
        await check_pvc_exists(name="ark-server-a", namespace=namespace, logger=Mock())
        is False
    )
    assert (
        await check_pvc_exists(name="ark-server-b", namespace=namespace, logger=Mock())
        is False
    )
    assert (
        await check_pvc_exists(name="ark-data", namespace=namespace, logger=Mock())
        is False
    )

    await update_cluster(
        name="ark",
        namespace=kube.namespace,
        spec=spec,
        logger=Mock(),
        allow_existing=False,
    )

    assert (
        await check_pvc_exists(name="ark-server-a", namespace=namespace, logger=Mock())
        is True
    )
    assert (
        await check_pvc_exists(name="ark-server-b", namespace=namespace, logger=Mock())
        is True
    )
    assert (
        await check_pvc_exists(name="ark-data", namespace=namespace, logger=Mock())
        is True
    )
