"""Test k8s functions."""

from __future__ import annotations

from http import HTTPStatus
from unittest.mock import AsyncMock, Mock

import pytest
import yaml
from aiofiles import open as aopen
from kubernetes_asyncio.client import ApiException

from ark_operator.exceptions import K8sError
from ark_operator.k8s.crds import (
    CRD_FILE,
    are_crds_installed,
    install_crds,
    uninstall_crds,
)


@pytest.mark.usefixtures("k8s_v1_ext_client")
@pytest.mark.asyncio
async def test_are_crds_installed() -> None:
    """Test are_crds_installed."""

    assert await are_crds_installed() is True


@pytest.mark.asyncio
async def test_are_crds_installed_not_found(k8s_v1_ext_client: Mock) -> None:
    """Test are_crds_installed."""

    k8s_v1_ext_client.read_custom_resource_definition = AsyncMock(
        side_effect=ApiException(status=HTTPStatus.NOT_FOUND)
    )

    assert await are_crds_installed() is False


@pytest.mark.asyncio
async def test_are_crds_installed_error(k8s_v1_ext_client: Mock) -> None:
    """Test are_crds_installed."""

    k8s_v1_ext_client.read_custom_resource_definition = AsyncMock(
        side_effect=ApiException(status=HTTPStatus.BAD_REQUEST)
    )

    with pytest.raises(ApiException):
        await are_crds_installed()


@pytest.mark.asyncio
async def test_uninstall_crds(k8s_v1_ext_client: Mock) -> None:
    """Test uninstall_crds."""

    await uninstall_crds()

    k8s_v1_ext_client.delete_custom_resource_definition.assert_awaited_once_with(
        "arkclusters.mort.is"
    )


@pytest.mark.asyncio
async def test_uninstall_crds_not_installed(k8s_v1_ext_client: Mock) -> None:
    """Test uninstall_crds."""

    k8s_v1_ext_client.read_custom_resource_definition = AsyncMock(
        side_effect=ApiException(status=HTTPStatus.NOT_FOUND)
    )

    with pytest.raises(K8sError):
        await uninstall_crds()

    k8s_v1_ext_client.delete_custom_resource_definition.assert_not_awaited()


@pytest.mark.asyncio
async def test_install_crds(k8s_v1_ext_client: Mock) -> None:
    """Test install_crds."""

    k8s_v1_ext_client.read_custom_resource_definition = AsyncMock(
        side_effect=ApiException(status=HTTPStatus.NOT_FOUND)
    )

    async with aopen(CRD_FILE) as f:
        crds = yaml.safe_load(await f.read())

    await install_crds()

    k8s_v1_ext_client.create_custom_resource_definition.assert_awaited_once_with(
        body=crds
    )


@pytest.mark.asyncio
async def test_install_crds_installed(k8s_v1_ext_client: Mock) -> None:
    """Test install_crds."""

    with pytest.raises(K8sError):
        await install_crds()

    k8s_v1_ext_client.create_custom_resource_definition.assert_not_awaited()


@pytest.mark.asyncio
async def test_install_crds_force(k8s_v1_ext_client: Mock) -> None:
    """Test install_crds."""

    async with aopen(CRD_FILE) as f:
        crds = yaml.safe_load(await f.read())

    await install_crds(force=True)

    k8s_v1_ext_client.delete_custom_resource_definition.assert_awaited_once_with(
        "arkclusters.mort.is"
    )
    k8s_v1_ext_client.create_custom_resource_definition.assert_awaited_once_with(
        body=crds
    )
