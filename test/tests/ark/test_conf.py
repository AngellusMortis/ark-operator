"""Test ARK config."""

from http import HTTPStatus
from unittest.mock import ANY, Mock

import pytest
from kubernetes_asyncio.client import ApiException

from ark_operator.ark import create_secrets, delete_secrets, get_map_envs
from ark_operator.data import ArkClusterSettings, ArkClusterSpec
from ark_operator.utils import VERSION


@pytest.mark.asyncio
async def test_create_secrets(k8s_v1_client: Mock) -> None:
    """Test create_secrets."""

    k8s_v1_client.read_namespaced_secret.side_effect = ApiException(
        status=HTTPStatus.NOT_FOUND
    )

    assert await create_secrets(name="test", namespace="test") is True

    k8s_v1_client.read_namespaced_secret.assert_awaited_once_with(
        name="test-cluster-secrets", namespace="test"
    )
    k8s_v1_client.create_namespaced_secret.assert_awaited_with(
        namespace="test",
        body={
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": "test-cluster-secrets",
                "labels": {
                    "app.kubernetes.io/name": "secrets",
                    "app.kubernetes.io/instance": "test",
                    "app.kubernetes.io/version": VERSION.replace("+", "-"),
                    "app.kubernetes.io/component": "secrets",
                    "app.kubernetes.io/part-of": "ark-operator",
                    "app.kubernetes.io/managed-by": "ark-operator",
                },
            },
            "type": "Opaque",
            "stringdata": {
                "ARK_SERVER_RCON_PASSWORD": ANY,
            },
        },
    )


@pytest.mark.asyncio
async def test_create_secrets_existing(k8s_v1_client: Mock) -> None:
    """Test create_secrets."""

    assert await create_secrets(name="test", namespace="test") is False

    k8s_v1_client.read_namespaced_secret.assert_awaited_once_with(
        name="test-cluster-secrets", namespace="test"
    )
    k8s_v1_client.create_namespaced_secret.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_secrets(k8s_v1_client: Mock) -> None:
    """Test delete_secrets."""

    await delete_secrets(name="test", namespace="test")

    k8s_v1_client.delete_namespaced_secret.assert_awaited_once_with(
        name="test-cluster-secrets", namespace="test"
    )


@pytest.mark.parametrize(
    ("global_settings", "global_cm", "map_cm", "map_id", "expected_envs"),
    [
        (
            ArkClusterSettings(),
            None,
            None,
            "TheIsland_WP",
            {
                "ARK_SERVER_MAP": "TheIsland_WP",
                "ARK_SERVER_SESSION_NAME": "ASA - The Island",
                "ARK_SERVER_AUTO_UPDATE": "false",
                "ARK_SERVER_MAX_PLAYERS": "70",
                "ARK_SERVER_CLUSTER_ID": "ark-cluster",
                "ARK_SERVER_BATTLEYE": "true",
                "ARK_SERVER_ALLOWED_PLATFORMS": "ALL",
                "ARK_SERVER_WHITELIST": "false",
            },
        ),
        (
            ArkClusterSettings(
                params=["Test", "Test2"], opts=["opt", "opt2"], mods=[123, 1234]
            ),
            None,
            None,
            "TheIsland_WP",
            {
                "ARK_SERVER_MAP": "TheIsland_WP",
                "ARK_SERVER_SESSION_NAME": "ASA - The Island",
                "ARK_SERVER_AUTO_UPDATE": "false",
                "ARK_SERVER_MAX_PLAYERS": "70",
                "ARK_SERVER_CLUSTER_ID": "ark-cluster",
                "ARK_SERVER_BATTLEYE": "true",
                "ARK_SERVER_ALLOWED_PLATFORMS": "ALL",
                "ARK_SERVER_WHITELIST": "false",
                "ARK_SERVER_PARAMS": "Test,Test2",
                "ARK_SERVER_OPTS": "opt,opt2",
                "ARK_SERVER_MODS": "123,1234",
            },
        ),
        (
            ArkClusterSettings(
                params=["Test", "Test2"], opts=["opt", "opt2"], mods=[123, 1234]
            ),
            None,
            None,
            "BobsMissions_WP",
            {
                "ARK_SERVER_MAP": "BobsMissions_WP",
                "ARK_SERVER_SESSION_NAME": "ASA - Club Ark",
                "ARK_SERVER_AUTO_UPDATE": "false",
                "ARK_SERVER_MAX_PLAYERS": "70",
                "ARK_SERVER_CLUSTER_ID": "ark-cluster",
                "ARK_SERVER_BATTLEYE": "true",
                "ARK_SERVER_ALLOWED_PLATFORMS": "ALL",
                "ARK_SERVER_WHITELIST": "false",
            },
        ),
        (
            ArkClusterSettings(
                session_name_format="{map_name}",
                multihome_ip="1.1.1.1",
                max_players=10,
                cluster_id="test",
                battleye=False,
                allowed_platforms=["XSX"],
                whitelist=True,
            ),
            None,
            None,
            "TheIsland_WP",
            {
                "ARK_SERVER_MAP": "TheIsland_WP",
                "ARK_SERVER_SESSION_NAME": "The Island",
                "ARK_SERVER_AUTO_UPDATE": "false",
                "ARK_SERVER_MAX_PLAYERS": "10",
                "ARK_SERVER_CLUSTER_ID": "test",
                "ARK_SERVER_BATTLEYE": "false",
                "ARK_SERVER_ALLOWED_PLATFORMS": "XSX",
                "ARK_SERVER_WHITELIST": "true",
                "ARK_SERVER_MULTIHOME": "1.1.1.1",
            },
        ),
        (
            ArkClusterSettings(
                session_name_format="{map_name}",
                multihome_ip="1.1.1.1",
                max_players=10,
                cluster_id="test",
                battleye=False,
                allowed_platforms=["XSX"],
                whitelist=True,
                mods=[123, 1234],
            ),
            {"ARK_SERVER_MODS": "456,234"},
            None,
            "TheIsland_WP",
            {
                "ARK_SERVER_MAP": "TheIsland_WP",
                "ARK_SERVER_SESSION_NAME": "The Island",
                "ARK_SERVER_AUTO_UPDATE": "false",
                "ARK_SERVER_MAX_PLAYERS": "10",
                "ARK_SERVER_CLUSTER_ID": "test",
                "ARK_SERVER_BATTLEYE": "false",
                "ARK_SERVER_ALLOWED_PLATFORMS": "XSX",
                "ARK_SERVER_WHITELIST": "true",
                "ARK_SERVER_MULTIHOME": "1.1.1.1",
                "ARK_SERVER_MODS": "456,234",
            },
        ),
        (
            ArkClusterSettings(
                session_name_format="{map_name}",
                multihome_ip="1.1.1.1",
                max_players=10,
                cluster_id="test",
                battleye=False,
                allowed_platforms=["XSX"],
                whitelist=True,
                mods=[123, 1234],
            ),
            {"ARK_SERVER_MODS": "456,234"},
            None,
            "BobsMissions_WP",
            {
                "ARK_SERVER_MAP": "BobsMissions_WP",
                "ARK_SERVER_SESSION_NAME": "Club Ark",
                "ARK_SERVER_AUTO_UPDATE": "false",
                "ARK_SERVER_MAX_PLAYERS": "10",
                "ARK_SERVER_CLUSTER_ID": "test",
                "ARK_SERVER_BATTLEYE": "false",
                "ARK_SERVER_ALLOWED_PLATFORMS": "XSX",
                "ARK_SERVER_WHITELIST": "true",
                "ARK_SERVER_MULTIHOME": "1.1.1.1",
            },
        ),
        (
            ArkClusterSettings(
                session_name_format="{map_name}",
                multihome_ip="1.1.1.1",
                max_players=10,
                cluster_id="test",
                battleye=False,
                allowed_platforms=["XSX"],
                whitelist=True,
                mods=[123, 1234],
            ),
            {"ARK_SERVER_MODS": "456,234"},
            {"ARK_SERVER_MODS": "222,333"},
            "TheIsland_WP",
            {
                "ARK_SERVER_MAP": "TheIsland_WP",
                "ARK_SERVER_SESSION_NAME": "The Island",
                "ARK_SERVER_AUTO_UPDATE": "false",
                "ARK_SERVER_MAX_PLAYERS": "10",
                "ARK_SERVER_CLUSTER_ID": "test",
                "ARK_SERVER_BATTLEYE": "false",
                "ARK_SERVER_ALLOWED_PLATFORMS": "XSX",
                "ARK_SERVER_WHITELIST": "true",
                "ARK_SERVER_MULTIHOME": "1.1.1.1",
                "ARK_SERVER_MODS": "222,333",
            },
        ),
        (
            ArkClusterSettings(
                session_name_format="{map_name}",
                multihome_ip="1.1.1.1",
                max_players=10,
                cluster_id="test",
                battleye=False,
                allowed_platforms=["XSX"],
                whitelist=True,
                mods=[123, 1234],
            ),
            {"ARK_SERVER_MODS": "456,234"},
            {"ARK_SERVER_MODS": "222,333"},
            "BobsMissions_WP",
            {
                "ARK_SERVER_MAP": "BobsMissions_WP",
                "ARK_SERVER_SESSION_NAME": "Club Ark",
                "ARK_SERVER_AUTO_UPDATE": "false",
                "ARK_SERVER_MAX_PLAYERS": "10",
                "ARK_SERVER_CLUSTER_ID": "test",
                "ARK_SERVER_BATTLEYE": "false",
                "ARK_SERVER_ALLOWED_PLATFORMS": "XSX",
                "ARK_SERVER_WHITELIST": "true",
                "ARK_SERVER_MULTIHOME": "1.1.1.1",
                "ARK_SERVER_MODS": "222,333",
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_get_map_envs(  # noqa: PLR0913
    k8s_v1_client: Mock,
    global_settings: ArkClusterSettings,
    global_cm: dict[str, str] | None,
    map_cm: dict[str, str] | None,
    map_id: str,
    expected_envs: dict[str, str],
) -> None:
    """Test get_map_envs."""

    side_effect = []
    if global_cm is None:
        side_effect.append(ApiException(status=HTTPStatus.NOT_FOUND))
    else:
        mock = Mock()
        mock.data = global_cm
        side_effect.append(mock)
    if map_cm is None:
        side_effect.append(ApiException(status=HTTPStatus.NOT_FOUND))
    else:
        mock = Mock()
        mock.data = map_cm
        side_effect.append(mock)

    k8s_v1_client.read_namespaced_config_map.side_effect = side_effect
    spec = ArkClusterSpec(global_settings=global_settings)
    assert (
        await get_map_envs(name="test", namespace="test", spec=spec, map_id=map_id)
        == expected_envs
    )
