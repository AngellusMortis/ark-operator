"""Ark PVC features."""

from http import HTTPStatus
from unittest.mock import ANY, AsyncMock, Mock

import kopf
import pytest
from kubernetes_asyncio.client import ApiException

from ark_operator.ark import check_init_job, create_init_job
from ark_operator.data import ArkClusterSpec, ArkClusterStatus
from ark_operator.utils import VERSION


@pytest.mark.asyncio
async def test_check_init_job(k8s_v1_batch_client: Mock) -> None:
    """Test check_init_job."""

    obj = Mock()
    obj.status.failed = None
    obj.status.completion_time = True

    k8s_v1_batch_client.read_namespaced_job.return_value = obj

    assert await check_init_job(name="test", namespace="test") is True

    k8s_v1_batch_client.read_namespaced_job.assert_awaited_once_with(
        name="test-init", namespace="test"
    )
    k8s_v1_batch_client.delete_namespaced_job.assert_awaited_once_with(
        name="test-init", namespace="test", propagation_policy="Foreground"
    )


@pytest.mark.asyncio
async def test_check_init_job_force(k8s_v1_batch_client: Mock) -> None:
    """Test check_init_job."""

    obj = Mock()
    obj.status.failed = None
    obj.status.completion_time = None

    k8s_v1_batch_client.read_namespaced_job.return_value = obj

    assert (
        await check_init_job(name="test", namespace="test", force_delete=True) is False
    )

    k8s_v1_batch_client.read_namespaced_job.assert_awaited_once_with(
        name="test-init", namespace="test"
    )


@pytest.mark.asyncio
async def test_check_init_job_not_complete(k8s_v1_batch_client: Mock) -> None:
    """Test check_init_job."""

    obj = Mock()
    obj.status.failed = 1
    obj.status.completion_time = None

    k8s_v1_batch_client.read_namespaced_job.return_value = obj

    with pytest.raises(kopf.TemporaryError):
        await check_init_job(name="test", namespace="test")

    k8s_v1_batch_client.read_namespaced_job.assert_awaited_once_with(
        name="test-init", namespace="test"
    )
    k8s_v1_batch_client.delete_namespaced_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_init_job_failed(k8s_v1_batch_client: Mock) -> None:
    """Test check_init_job."""

    obj = Mock()
    obj.status.failed = 10
    obj.status.completion_time = None

    k8s_v1_batch_client.read_namespaced_job.return_value = obj

    with pytest.raises(kopf.PermanentError):
        await check_init_job(name="test", namespace="test")

    k8s_v1_batch_client.read_namespaced_job.assert_awaited_once_with(
        name="test-init", namespace="test"
    )
    k8s_v1_batch_client.delete_namespaced_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_init_not_found(k8s_v1_batch_client: Mock) -> None:
    """Test check_init_job."""

    k8s_v1_batch_client.read_namespaced_job.side_effect = ApiException(
        status=HTTPStatus.NOT_FOUND
    )

    assert await check_init_job(name="test", namespace="test") is False

    k8s_v1_batch_client.read_namespaced_job.assert_awaited_once_with(
        name="test-init", namespace="test"
    )
    k8s_v1_batch_client.delete_namespaced_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_init_api_error(k8s_v1_batch_client: Mock) -> None:
    """Test check_init_job."""

    k8s_v1_batch_client.read_namespaced_job.side_effect = ApiException(
        status=HTTPStatus.BAD_REQUEST
    )

    with pytest.raises(kopf.TemporaryError):
        await check_init_job(name="test", namespace="test")

    k8s_v1_batch_client.read_namespaced_job.assert_awaited_once_with(
        name="test-init", namespace="test"
    )
    k8s_v1_batch_client.delete_namespaced_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_init_job_error(k8s_v1_batch_client: Mock) -> None:
    """Test create_init_job."""

    k8s_v1_batch_client.create_namespaced_job = AsyncMock(side_effect=Exception("test"))

    spec = ArkClusterSpec()
    status = ArkClusterStatus()

    with pytest.raises(kopf.PermanentError):
        await create_init_job(name="test", namespace="test", spec=spec, status=status)


@pytest.mark.asyncio
async def test_create_init_job(k8s_v1_batch_client: Mock) -> None:
    """Test create_init_job."""

    spec = ArkClusterSpec()
    status = ArkClusterStatus()
    await create_init_job(name="test", namespace="test", spec=spec, status=status)

    k8s_v1_batch_client.create_namespaced_job.assert_awaited_once_with(
        namespace="test",
        body={
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": "test-init",
                "labels": {
                    "app.kubernetes.io/name": "arkctl",
                    "app.kubernetes.io/instance": "test",
                    "app.kubernetes.io/version": VERSION.replace("+", "-"),
                    "app.kubernetes.io/component": "init-job",
                    "app.kubernetes.io/part-of": "ark-operator",
                    "app.kubernetes.io/managed-by": "ark-operator",
                },
            },
            "spec": {
                "backoffLimit": 3,
                "template": {
                    "spec": {
                        "restartPolicy": "Never",
                        "containers": [
                            {
                                "name": "job",
                                "image": "ghcr.io/angellusmortis/ark-server:master",
                                "imagePullPolicy": "Always",
                                "command": [
                                    "arkctl",
                                    "cluster",
                                    "init-volumes",
                                    "/mnt",
                                ],
                                "volumeMounts": [
                                    {"name": "data", "mountPath": "/mnt/data"},
                                    {"name": "server-a", "mountPath": "/mnt/server-a"},
                                    {"name": "server-b", "mountPath": "/mnt/server-b"},
                                ],
                                "env": [
                                    {
                                        "name": "ARK_CLUSTER_NAME",
                                        "value": "test",
                                    },
                                    {
                                        "name": "ARK_CLUSTER_NAMESPACE",
                                        "value": "test",
                                    },
                                    {
                                        "name": "ARK_CLUSTER_SPEC",
                                        "value": ANY,
                                    },
                                    {
                                        "name": "ARK_CLUSTER_STATUS",
                                        "value": ANY,
                                    },
                                    {
                                        "name": "ARK_SERVER_HOST",
                                        "value": "127.0.0.1",
                                    },
                                    {
                                        "name": "ARK_SERVER_RCON_PASSWORD",
                                        "value": "notactuallythepassword",
                                    },
                                ],
                                "securityContext": {
                                    "runAsUser": 65535,
                                    "runAsGroup": 65535,
                                    "allowPrivilegeEscalation": False,
                                    "runAsNonRoot": True,
                                    "seccompProfile": {"type": "RuntimeDefault"},
                                    "capabilities": {"drop": ["ALL"]},
                                },
                            }
                        ],
                        "initContainers": [
                            {
                                "name": "init-perms",
                                "image": "debian:12.8-slim",
                                "imagePullPolicy": "IfNotPresent",
                                "command": [
                                    "sh",
                                    "-c",
                                    "chown -R 65535:65535 /mnt/data /mnt/server-a /mnt/server-b",
                                ],
                                "volumeMounts": [
                                    {"name": "data", "mountPath": "/mnt/data"},
                                    {"name": "server-a", "mountPath": "/mnt/server-a"},
                                    {"name": "server-b", "mountPath": "/mnt/server-b"},
                                ],
                            }
                        ],
                        "volumes": [
                            {
                                "name": "data",
                                "persistentVolumeClaim": {
                                    "claimName": "test-data",
                                },
                            },
                            {
                                "name": "server-a",
                                "persistentVolumeClaim": {
                                    "claimName": "test-server-a",
                                },
                            },
                            {
                                "name": "server-b",
                                "persistentVolumeClaim": {
                                    "claimName": "test-server-b",
                                },
                            },
                        ],
                    }
                },
            },
        },
    )


@pytest.mark.asyncio
async def test_create_init_job_dry_run(k8s_v1_batch_client: Mock) -> None:
    """Test create_init_job."""

    spec = ArkClusterSpec()
    status = ArkClusterStatus()
    await create_init_job(
        name="test", namespace="test", spec=spec, status=status, dry_run=True
    )

    k8s_v1_batch_client.create_namespaced_job.assert_awaited_once_with(
        namespace="test",
        body={
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": "test-init",
                "labels": {
                    "app.kubernetes.io/name": "arkctl",
                    "app.kubernetes.io/instance": "test",
                    "app.kubernetes.io/version": VERSION.replace("+", "-"),
                    "app.kubernetes.io/component": "init-job",
                    "app.kubernetes.io/part-of": "ark-operator",
                    "app.kubernetes.io/managed-by": "ark-operator",
                },
            },
            "spec": {
                "backoffLimit": 3,
                "template": {
                    "spec": {
                        "restartPolicy": "Never",
                        "containers": [
                            {
                                "name": "job",
                                "image": "ghcr.io/angellusmortis/ark-server:master",
                                "imagePullPolicy": "Always",
                                "command": [
                                    "arkctl",
                                    "cluster",
                                    "init-volumes",
                                    "/mnt",
                                ],
                                "volumeMounts": [
                                    {"name": "data", "mountPath": "/mnt/data"},
                                    {"name": "server-a", "mountPath": "/mnt/server-a"},
                                    {"name": "server-b", "mountPath": "/mnt/server-b"},
                                ],
                                "env": [
                                    {
                                        "name": "ARK_OP_DRY_RUN",
                                        "value": "true",
                                    },
                                    {
                                        "name": "ARK_CLUSTER_NAME",
                                        "value": "test",
                                    },
                                    {
                                        "name": "ARK_CLUSTER_NAMESPACE",
                                        "value": "test",
                                    },
                                    {
                                        "name": "ARK_CLUSTER_SPEC",
                                        "value": ANY,
                                    },
                                    {
                                        "name": "ARK_CLUSTER_STATUS",
                                        "value": ANY,
                                    },
                                    {
                                        "name": "ARK_SERVER_HOST",
                                        "value": "127.0.0.1",
                                    },
                                    {
                                        "name": "ARK_SERVER_RCON_PASSWORD",
                                        "value": "notactuallythepassword",
                                    },
                                ],
                                "securityContext": {
                                    "runAsUser": 65535,
                                    "runAsGroup": 65535,
                                    "allowPrivilegeEscalation": False,
                                    "runAsNonRoot": True,
                                    "seccompProfile": {"type": "RuntimeDefault"},
                                    "capabilities": {"drop": ["ALL"]},
                                },
                            }
                        ],
                        "initContainers": [
                            {
                                "name": "init-perms",
                                "image": "debian:12.8-slim",
                                "imagePullPolicy": "IfNotPresent",
                                "command": [
                                    "sh",
                                    "-c",
                                    "chown -R 65535:65535 /mnt/data /mnt/server-a /mnt/server-b",
                                ],
                                "volumeMounts": [
                                    {"name": "data", "mountPath": "/mnt/data"},
                                    {"name": "server-a", "mountPath": "/mnt/server-a"},
                                    {"name": "server-b", "mountPath": "/mnt/server-b"},
                                ],
                            }
                        ],
                        "volumes": [
                            {
                                "name": "data",
                                "persistentVolumeClaim": {
                                    "claimName": "test-data",
                                },
                            },
                            {
                                "name": "server-a",
                                "persistentVolumeClaim": {
                                    "claimName": "test-server-a",
                                },
                            },
                            {
                                "name": "server-b",
                                "persistentVolumeClaim": {
                                    "claimName": "test-server-b",
                                },
                            },
                        ],
                    }
                },
            },
        },
    )
