"""Test creating server pods."""

from __future__ import annotations

from copy import deepcopy
from http import HTTPStatus
from unittest.mock import ANY, AsyncMock, Mock, patch

import pytest
from kubernetes_asyncio.client import ApiException

from ark_operator.ark import create_server_pod, delete_server_pod
from ark_operator.data import ArkClusterSpec
from ark_operator.utils import VERSION

_ENVS = {"ARK_SERVER_GAME_PORT": "7777", "ARK_SERVER_RCON_PORT": "27020"}
_SERVER_POD = {
    "apiVersion": "v1",
    "kind": "Pod",
    "metadata": {
        "name": "test-the-island",
        "labels": {
            "app.kubernetes.io/name": "the-island",
            "app.kubernetes.io/instance": "test",
            "app.kubernetes.io/version": VERSION.replace("+", "-"),
            "app.kubernetes.io/component": "server",
            "app.kubernetes.io/part-of": "ark-operator",
            "app.kubernetes.io/managed-by": "ark-operator",
        },
    },
    "spec": {
        "restartPolicy": "Always",
        "containers": [
            {
                "name": "ark",
                "image": "ghcr.io/angellusmortis/ark-server:master",
                "imagePullPolicy": "Always",
                "command": ["/entrypoint"],
                "securityContext": {
                    "runAsUser": 65535,
                    "runAsGroup": 65535,
                    "fsGroup": 65535,
                    "allowPrivilegeEscalation": False,
                },
                "ports": [
                    {
                        "containerPort": 7777,
                        "name": "ark-the-island",
                        "protocol": "UDP",
                    },
                    {
                        "containerPort": 27020,
                        "name": "rcon-the-island",
                        "protocol": "TCP",
                    },
                ],
                "envFrom": [{"secretRef": {"name": "test-cluster-secrets"}}],
                "env": [
                    {"name": "ARK_CLUSTER_NAME", "value": "test"},
                    {"name": "ARK_CLUSTER_NAMESPACE", "value": "testing"},
                    {"name": "ARK_CLUSTER_SPEC", "value": ANY},
                    {"name": "ARK_SERVER_HOST", "value": "127.0.0.1"},
                    {"name": "ARK_SERVER_GAME_PORT", "value": "7777"},
                    {"name": "ARK_SERVER_RCON_PORT", "value": "27020"},
                ],
                "volumeMounts": [
                    {
                        "mountPath": "/srv/ark/server",
                        "name": "server",
                        "readOnly": True,
                    },
                    {"mountPath": "/srv/ark/data", "name": "data"},
                    {
                        "mountPath": "/srv/ark/server/ark/ShooterGame/Saved",
                        "name": "data",
                        "subPath": "maps/TheIsland_WP/saved",
                    },
                    {
                        "mountPath": "/srv/ark/server/ark/ShooterGame/Binaries/Win64/ShooterGame",
                        "name": "data",
                        "subPath": "maps/TheIsland_WP/mods",
                    },
                    {
                        "mountPath": "/srv/ark/server/ark/ShooterGame/Binaries/Win64/PlayersExclusiveJoinList.txt",
                        "name": "data",
                        "subPath": "lists/PlayersExclusiveJoinList.txt",
                    },
                    {
                        "mountPath": "/srv/ark/server/ark/ShooterGame/Binaries/Win64/PlayersJoinNoCheckList.txt",
                        "name": "data",
                        "subPath": "lists/PlayersJoinNoCheckList.txt",
                    },
                ],
                "readinessProbe": {
                    "exec": {
                        "command": [
                            "sh",
                            "-c",
                            "arkctl server --host 127.0.0.1 rcon ListPlayers",
                        ],
                    },
                    "initialDelaySeconds": 20,
                    "timeoutSeconds": 5,
                    "periodSeconds": 5,
                    "failureThreshold": 3,
                    "successThreshold": 1,
                },
                "startupProbe": {
                    "exec": {
                        "command": [
                            "sh",
                            "-c",
                            'test -f "/srv/ark/server/ark/ShooterGame/Saved/.started"',
                        ],
                    },
                    "initialDelaySeconds": 5,
                    "failureThreshold": 360,
                    "periodSeconds": 10,
                },
            }
        ],
        "volumes": [
            {"name": "server", "persistentVolumeClaim": {"claimName": "test-server-a"}},
            {"name": "data", "persistentVolumeClaim": {"claimName": "test-data"}},
        ],
    },
}


@patch(
    "ark_operator.ark.server.get_map_envs",
    AsyncMock(return_value=_ENVS),
)
@pytest.mark.asyncio
async def test_create_server_pod(k8s_v1_client: Mock) -> None:
    """Test create_server_pod."""

    pod = deepcopy(_SERVER_POD)
    k8s_v1_client.read_namespaced_pod.side_effect = ApiException(
        status=HTTPStatus.NOT_FOUND
    )
    spec = ArkClusterSpec()

    assert (
        await create_server_pod(
            name="test",
            namespace="testing",
            map_id="TheIsland_WP",
            active_volume="server-a",
            spec=spec,
        )
        is True
    )

    k8s_v1_client.read_namespaced_pod.assert_awaited_once_with(
        namespace="testing", name="test-the-island"
    )
    k8s_v1_client.create_namespaced_pod.assert_awaited_once()
    actual = k8s_v1_client.create_namespaced_pod.call_args_list[0].kwargs["body"]
    assert actual == pod


@patch(
    "ark_operator.ark.server.get_map_envs",
    AsyncMock(return_value=_ENVS),
)
@pytest.mark.asyncio
async def test_create_server_pod_exists(k8s_v1_client: Mock) -> None:
    """Test create_server_pod."""

    spec = ArkClusterSpec()

    assert (
        await create_server_pod(
            name="test",
            namespace="testing",
            map_id="TheIsland_WP",
            active_volume="server-a",
            spec=spec,
        )
        is False
    )

    k8s_v1_client.read_namespaced_pod.assert_awaited_once_with(
        namespace="testing", name="test-the-island"
    )
    k8s_v1_client.create_namespaced_pod.assert_not_awaited()


@patch(
    "ark_operator.ark.server.get_map_envs",
    AsyncMock(return_value=_ENVS),
)
@pytest.mark.asyncio
async def test_create_server_pod_force_create(k8s_v1_client: Mock) -> None:
    """Test create_server_pod."""

    pod = deepcopy(_SERVER_POD)
    spec = ArkClusterSpec()

    assert (
        await create_server_pod(
            name="test",
            namespace="testing",
            map_id="TheIsland_WP",
            active_volume="server-a",
            spec=spec,
            force_create=True,
        )
        is True
    )

    k8s_v1_client.read_namespaced_pod.assert_awaited_once_with(
        namespace="testing", name="test-the-island"
    )
    k8s_v1_client.patch_namespaced_pod.assert_awaited_once()
    actual = k8s_v1_client.patch_namespaced_pod.call_args_list[0].kwargs["body"]
    assert actual == pod


@pytest.mark.asyncio
async def test_delete_server_pod(k8s_v1_client: Mock) -> None:
    """Test delete_server_pod."""

    await delete_server_pod(name="test", namespace="testing", map_id="TheIsland_WP")

    k8s_v1_client.delete_namespaced_pod.assert_awaited_once_with(
        name="test-the-island", namespace="testing"
    )
