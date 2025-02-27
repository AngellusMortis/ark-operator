"""Test k8s functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import kopf
import pytest

from ark_operator.k8s import (
    check_pvc_exists,
    create_pvc,
    delete_pvc,
    resize_pvc,
)
from ark_operator.utils import VERSION


@pytest.mark.asyncio(loop_scope="function")
async def test_resize_pvc(k8s_v1_client: Mock) -> None:
    """Test resizing a PVC."""

    assert (
        await resize_pvc(
            name="test", namespace="test", new_size="60Gi", size="50Gi", logger=Mock()
        )
        is True
    )

    k8s_v1_client.patch_namespaced_persistent_volume_claim.assert_awaited_once_with(
        name="test",
        namespace="test",
        body={"spec": {"resources": {"requests": {"storage": "60Gi"}}}},
    )


@pytest.mark.asyncio(loop_scope="function")
async def test_resize_pvc_too_small(k8s_v1_client: Mock) -> None:
    """Test resizing a PVC."""

    with pytest.raises(kopf.PermanentError):
        await resize_pvc(
            name="test", namespace="test", new_size="40Gi", size="50Gi", logger=Mock()
        )

    k8s_v1_client.patch_namespaced_persistent_volume_claim.assert_not_awaited()


@pytest.mark.asyncio(loop_scope="function")
async def test_resize_pvc_same_size(k8s_v1_client: Mock) -> None:
    """Test resizing a PVC."""

    assert (
        await resize_pvc(
            name="test", namespace="test", new_size="50Gi", size="50Gi", logger=Mock()
        )
        is False
    )

    k8s_v1_client.patch_namespaced_persistent_volume_claim.assert_not_awaited()


@pytest.mark.asyncio(loop_scope="function")
async def test_resize_pvc_error(k8s_v1_client: Mock) -> None:
    """Test resizing a PVC."""

    k8s_v1_client.patch_namespaced_persistent_volume_claim.side_effect = Exception(
        "test"
    )

    with pytest.raises(kopf.PermanentError):
        await resize_pvc(
            name="test", namespace="test", new_size="60Gi", size="50Gi", logger=Mock()
        )

    k8s_v1_client.patch_namespaced_persistent_volume_claim.assert_awaited_once_with(
        name="test",
        namespace="test",
        body={"spec": {"resources": {"requests": {"storage": "60Gi"}}}},
    )


@pytest.mark.asyncio(loop_scope="function")
async def test_check_pvc_exists(k8s_v1_client: Mock) -> None:
    """Test checking if PVC exist."""

    assert await check_pvc_exists(name="test", namespace="test", logger=Mock()) is True

    k8s_v1_client.read_namespaced_persistent_volume_claim.assert_awaited_once_with(
        name="test", namespace="test"
    )


@pytest.mark.asyncio(loop_scope="function")
async def test_check_pvc_exists_resize(k8s_v1_client: Mock) -> None:
    """Test checking if PVC exist."""

    mock_pvc = Mock()
    mock_pvc.spec.resources.requests = {"storage": "50Gi"}

    k8s_v1_client.read_namespaced_persistent_volume_claim = AsyncMock(
        return_value=mock_pvc
    )

    assert (
        await check_pvc_exists(
            name="test", namespace="test", logger=Mock(), new_size="60Gi"
        )
        is True
    )

    k8s_v1_client.patch_namespaced_persistent_volume_claim.assert_awaited_once_with(
        name="test",
        namespace="test",
        body={"spec": {"resources": {"requests": {"storage": "60Gi"}}}},
    )
    k8s_v1_client.read_namespaced_persistent_volume_claim.assert_awaited_once_with(
        name="test", namespace="test"
    )


@pytest.mark.asyncio(loop_scope="function")
async def test_check_pvc_exists_not_found(k8s_v1_client: Mock) -> None:
    """Test checking if PVC exist."""

    k8s_v1_client.read_namespaced_persistent_volume_claim.side_effect = Exception(
        "test"
    )

    assert (
        await check_pvc_exists(
            name="test", namespace="test", logger=Mock(), new_size="60Gi"
        )
        is False
    )

    k8s_v1_client.read_namespaced_persistent_volume_claim.assert_awaited_once_with(
        name="test", namespace="test"
    )


@pytest.mark.asyncio(loop_scope="function")
async def test_delete_pvc(k8s_v1_client: Mock) -> None:
    """Test deleting a PVC."""

    assert await delete_pvc(name="test", namespace="test", logger=Mock()) is True

    k8s_v1_client.delete_namespaced_persistent_volume_claim.assert_awaited_once_with(
        name="test",
        namespace="test",
        propagation_policy="Foreground",
        grace_period_seconds=5,
    )


@pytest.mark.asyncio(loop_scope="function")
async def test_delete_pvc_error(k8s_v1_client: Mock) -> None:
    """Test deleting a PVC."""

    k8s_v1_client.delete_namespaced_persistent_volume_claim.side_effect = Exception(
        "test"
    )

    assert await delete_pvc(name="test", namespace="test", logger=Mock()) is False

    k8s_v1_client.delete_namespaced_persistent_volume_claim.assert_awaited_once_with(
        name="test",
        namespace="test",
        propagation_policy="Foreground",
        grace_period_seconds=5,
    )


@pytest.mark.asyncio(loop_scope="function")
async def test_create_pvc(k8s_v1_client: Mock) -> None:
    """Test creating a PVC."""

    mock_pvc = Mock()
    mock_pvc.status.phase = "Bound"

    k8s_v1_client.read_namespaced_persistent_volume_claim = AsyncMock(
        return_value=mock_pvc
    )

    assert (
        await create_pvc(
            name="test",
            instance_name="testing",
            namespace="test",
            size="50Gi",
            logger=Mock(),
        )
        is True
    )

    k8s_v1_client.create_namespaced_persistent_volume_claim.assert_awaited_once_with(
        namespace="test",
        body={
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": "testing-test",
                "labels": {
                    "app.kubernetes.io/name": "pvc",
                    "app.kubernetes.io/instance": "testing",
                    "app.kubernetes.io/version": VERSION.replace("+", "-"),
                    "app.kubernetes.io/component": "test",
                    "app.kubernetes.io/part-of": "ark-operator",
                    "app.kubernetes.io/managed-by": "ark-operator",
                },
            },
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "50Gi"}},
            },
        },
    )


@pytest.mark.asyncio(loop_scope="function")
async def test_create_pvc_storage_class(k8s_v1_client: Mock) -> None:
    """Test creating a PVC."""

    mock_pvc = Mock()
    mock_pvc.status.phase = "Bound"

    k8s_v1_client.read_namespaced_persistent_volume_claim = AsyncMock(
        return_value=mock_pvc
    )

    assert (
        await create_pvc(
            name="test",
            instance_name="testing",
            namespace="test",
            size="50Gi",
            access_mode="ReadWriteMany",
            storage_class="longhorn",
            logger=Mock(),
            min_size="50Gi",
        )
        is True
    )

    k8s_v1_client.create_namespaced_persistent_volume_claim.assert_awaited_once_with(
        namespace="test",
        body={
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": "testing-test",
                "labels": {
                    "app.kubernetes.io/name": "pvc",
                    "app.kubernetes.io/instance": "testing",
                    "app.kubernetes.io/version": VERSION.replace("+", "-"),
                    "app.kubernetes.io/component": "test",
                    "app.kubernetes.io/part-of": "ark-operator",
                    "app.kubernetes.io/managed-by": "ark-operator",
                },
            },
            "spec": {
                "storageClassName": "longhorn",
                "accessModes": ["ReadWriteMany"],
                "resources": {"requests": {"storage": "50Gi"}},
            },
        },
    )


@pytest.mark.asyncio(loop_scope="function")
async def test_create_pvc_too_small(k8s_v1_client: Mock) -> None:
    """Test creating a PVC."""

    with pytest.raises(kopf.PermanentError):
        await create_pvc(
            name="test",
            instance_name="testing",
            namespace="test",
            size="40Gi",
            access_mode="ReadWriteMany",
            storage_class="longhorn",
            logger=Mock(),
            min_size="50Gi",
        )

    k8s_v1_client.create_namespaced_persistent_volume_claim.assert_not_awaited()


@pytest.mark.asyncio(loop_scope="function")
async def test_create_pvc_error(k8s_v1_client: Mock) -> None:
    """Test creating a PVC."""

    k8s_v1_client.create_namespaced_persistent_volume_claim.side_effect = Exception(
        "test"
    )

    with pytest.raises(kopf.PermanentError):
        await create_pvc(
            name="test",
            instance_name="testing",
            namespace="test",
            size="50Gi",
            logger=Mock(),
        )

    k8s_v1_client.create_namespaced_persistent_volume_claim.assert_awaited_once_with(
        namespace="test",
        body={
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": "testing-test",
                "labels": {
                    "app.kubernetes.io/name": "pvc",
                    "app.kubernetes.io/instance": "testing",
                    "app.kubernetes.io/version": VERSION.replace("+", "-"),
                    "app.kubernetes.io/component": "test",
                    "app.kubernetes.io/part-of": "ark-operator",
                    "app.kubernetes.io/managed-by": "ark-operator",
                },
            },
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "50Gi"}},
            },
        },
    )
