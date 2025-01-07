"""Ark PVC features."""

from http import HTTPStatus
from unittest.mock import AsyncMock, Mock

import kopf
import pytest
from kubernetes_asyncio.client import ApiException

from ark_operator.ark import check_init_job, create_init_job
from ark_operator.data import ArkClusterSpec


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

    with pytest.raises(kopf.PermanentError):
        await create_init_job(name="test", namespace="test", spec=spec)


@pytest.mark.asyncio
async def test_create_init_job(k8s_v1_batch_client: Mock) -> None:
    """Test create_init_job."""

    spec = ArkClusterSpec()
    await create_init_job(name="test", namespace="test", spec=spec)

    k8s_v1_batch_client.create_namespaced_job.assert_awaited_once_with(
        namespace="test",
        body={
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": "test-init",
                "labels": {
                    "app.kubernetes.io/name": "ark-operator",
                    "app.kubernetes.io/component": "init-job",
                    "app.kubernetes.io/part-of": "test",
                },
            },
            "spec": {
                "backoffLimit": 3,
                "template": {
                    "spec": {
                        "restartPolicy": "Never",
                        "containers": [
                            {
                                "name": "init-ark",
                                "image": "ghcr.io/angellusmortis/ark-operator:master",
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
                                        "name": "ARK_CLUSTER_SPEC",
                                        "value": '{"server":{"load_balancer_ip":null,"storage_class":null,"size":"50Gi","maps":["@canonical"],"persist":false,"game_port_start":7777,"rcon_port_start":27020,"all_maps":["BobsMissions_WP","TheIsland_WP","ScorchedEarth_WP","Aberration_WP","Extinction_WP"],"all_servers":{"BobsMissions_WP":{"map_id":"BobsMissions_WP","port":7777,"rcon_port":27020},"TheIsland_WP":{"map_id":"TheIsland_WP","port":7778,"rcon_port":27021},"ScorchedEarth_WP":{"map_id":"ScorchedEarth_WP","port":7779,"rcon_port":27022},"Aberration_WP":{"map_id":"Aberration_WP","port":7780,"rcon_port":27023},"Extinction_WP":{"map_id":"Extinction_WP","port":7781,"rcon_port":27024}}},"data":{"storage_class":null,"size":"50Gi","persist":true},"run_as_user":65535,"run_as_group":65535,"cluster":{"cluster_id":"ark-cluster"}}',
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
    await create_init_job(name="test", namespace="test", spec=spec, dry_run=True)

    k8s_v1_batch_client.create_namespaced_job.assert_awaited_once_with(
        namespace="test",
        body={
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": "test-init",
                "labels": {
                    "app.kubernetes.io/name": "ark-operator",
                    "app.kubernetes.io/component": "init-job",
                    "app.kubernetes.io/part-of": "test",
                },
            },
            "spec": {
                "backoffLimit": 3,
                "template": {
                    "spec": {
                        "restartPolicy": "Never",
                        "containers": [
                            {
                                "name": "init-ark",
                                "image": "ghcr.io/angellusmortis/ark-operator:master",
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
                                        "value": "True",
                                    },
                                    {
                                        "name": "ARK_CLUSTER_SPEC",
                                        "value": '{"server":{"load_balancer_ip":null,"storage_class":null,"size":"50Gi","maps":["@canonical"],"persist":false,"game_port_start":7777,"rcon_port_start":27020,"all_maps":["BobsMissions_WP","TheIsland_WP","ScorchedEarth_WP","Aberration_WP","Extinction_WP"],"all_servers":{"BobsMissions_WP":{"map_id":"BobsMissions_WP","port":7777,"rcon_port":27020},"TheIsland_WP":{"map_id":"TheIsland_WP","port":7778,"rcon_port":27021},"ScorchedEarth_WP":{"map_id":"ScorchedEarth_WP","port":7779,"rcon_port":27022},"Aberration_WP":{"map_id":"Aberration_WP","port":7780,"rcon_port":27023},"Extinction_WP":{"map_id":"Extinction_WP","port":7781,"rcon_port":27024}}},"data":{"storage_class":null,"size":"50Gi","persist":true},"run_as_user":65535,"run_as_group":65535,"cluster":{"cluster_id":"ark-cluster"}}',
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
