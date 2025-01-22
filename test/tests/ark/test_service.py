"""Test creating server pods."""

from __future__ import annotations

from copy import deepcopy
from http import HTTPStatus
from unittest.mock import Mock, call

import pytest
from kubernetes_asyncio.client import ApiException

from ark_operator.ark import create_services, delete_services
from ark_operator.data import ArkClusterSpec
from ark_operator.utils import VERSION

_GAME_SERVICE = {
    "apiVersion": "v1",
    "kind": "Service",
    "metadata": {
        "name": "test",
        "labels": {
            "app.kubernetes.io/name": "ark",
            "app.kubernetes.io/instance": "test",
            "app.kubernetes.io/version": VERSION.replace("+", "-"),
            "app.kubernetes.io/component": "service",
            "app.kubernetes.io/part-of": "ark-operator",
            "app.kubernetes.io/managed-by": "ark-operator",
        },
    },
    "spec": {
        "selector": {
            "app.kubernetes.io/instance": "test",
            "app.kubernetes.io/component": "server",
            "app.kubernetes.io/part-of": "ark-operator",
        },
        "ports": [
            {
                "name": "ark-club-ark",
                "port": 7777,
                "targetPort": "ark-club-ark",
                "protocol": "UDP",
            },
            {
                "name": "ark-island",
                "port": 7778,
                "targetPort": "ark-island",
                "protocol": "UDP",
            },
            {
                "name": "ark-se",
                "port": 7779,
                "targetPort": "ark-se",
                "protocol": "UDP",
            },
            {
                "name": "ark-aberration",
                "port": 7780,
                "targetPort": "ark-aberration",
                "protocol": "UDP",
            },
            {
                "name": "ark-extinction",
                "port": 7781,
                "targetPort": "ark-extinction",
                "protocol": "UDP",
            },
        ],
        "externalTrafficPolicy": "Local",
        "type": "LoadBalancer",
    },
}
_RCON_SERVICE = deepcopy(_GAME_SERVICE)
_RCON_SERVICE["metadata"]["name"] = "test-rcon"  # type: ignore[index]
_RCON_SERVICE["metadata"]["labels"]["app.kubernetes.io/name"] = "rcon"  # type: ignore[index]
_RCON_SERVICE["spec"]["ports"] = [  # type: ignore[index]
    {
        "name": "rcon-club-ark",
        "port": 27020,
        "targetPort": "rcon-club-ark",
        "protocol": "TCP",
    },
    {
        "name": "rcon-island",
        "port": 27021,
        "targetPort": "rcon-island",
        "protocol": "TCP",
    },
    {
        "name": "rcon-se",
        "port": 27022,
        "targetPort": "rcon-se",
        "protocol": "TCP",
    },
    {
        "name": "rcon-aberration",
        "port": 27023,
        "targetPort": "rcon-aberration",
        "protocol": "TCP",
    },
    {
        "name": "rcon-extinction",
        "port": 27024,
        "targetPort": "rcon-extinction",
        "protocol": "TCP",
    },
]


@pytest.mark.asyncio
async def test_create_services(k8s_v1_client: Mock) -> None:
    """Test create_services."""

    k8s_v1_client.read_namespaced_service.side_effect = ApiException(
        status=HTTPStatus.NOT_FOUND
    )
    spec = ArkClusterSpec()

    assert (
        await create_services(
            name="test",
            namespace="testing",
            spec=spec,
        )
        is True
    )

    assert len(k8s_v1_client.create_namespaced_service.call_args_list) == 2
    specs = [
        k8s_v1_client.create_namespaced_service.call_args_list[0].kwargs["body"],
        k8s_v1_client.create_namespaced_service.call_args_list[1].kwargs["body"],
    ]
    assert specs == [
        _GAME_SERVICE,
        _RCON_SERVICE,
    ]


@pytest.mark.asyncio
async def test_create_services_exists(k8s_v1_client: Mock) -> None:
    """Test create_services."""

    spec = ArkClusterSpec()

    assert await create_services(name="test", namespace="testing", spec=spec) is True

    assert len(k8s_v1_client.patch_namespaced_service.call_args_list) == 2
    specs = [
        k8s_v1_client.patch_namespaced_service.call_args_list[0].kwargs["body"],
        k8s_v1_client.patch_namespaced_service.call_args_list[1].kwargs["body"],
    ]
    assert specs == [
        _GAME_SERVICE,
        _RCON_SERVICE,
    ]


@pytest.mark.asyncio
async def test_delete_services_pod(k8s_v1_client: Mock) -> None:
    """Test delete_services."""

    await delete_services(name="test", namespace="testing")

    assert len(k8s_v1_client.delete_namespaced_service.call_args_list) == 2
    assert k8s_v1_client.delete_namespaced_service.call_args_list == [
        call(name="test", namespace="testing", propagation_policy="Foreground"),
        call(name="test-rcon", namespace="testing", propagation_policy="Foreground"),
    ]
