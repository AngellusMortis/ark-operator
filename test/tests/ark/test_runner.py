"""Test ARK server runner."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from aiofiles import open as aopen
from aiofiles import os as aos

from ark_operator.ark import ArkServer
from ark_operator.utils import touch_file

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path


class _RunFixture(NamedTuple):
    base_dir: Path
    mock_run: AsyncMock


async def _write_log(
    base_dir: Path, message: str, map_name: str = "TheIsland_WP"
) -> None:
    log_dir = base_dir / "data" / "maps" / map_name / "saved" / "Logs"

    async with aopen(log_dir / "ShooterGame.log", "a") as f:
        await f.write(message)


async def _assert_file_contents(file_path: Path, contents: str) -> None:
    async with aopen(file_path) as f:
        assert contents == await f.read()


async def _assert_config(
    base_dir: Path,
    config: str,
    filename: str = "GameUserSettings.ini",
    map_name: str = "TheIsland_WP",
) -> None:
    config_dir = (
        base_dir / "data" / "maps" / map_name / "saved" / "Config" / "WindowsServer"
    )
    await _assert_file_contents(config_dir / filename, config)


@pytest_asyncio.fixture(name="run_failure")
async def run_failure_fixture(temp_dir: Path) -> AsyncGenerator[_RunFixture]:
    """Fake a run for ASA server."""

    ark_dir = temp_dir / "ark"
    game_dir = ark_dir / "ShooterGame"
    binary_dir = game_dir / "Binaries" / "Win64"
    data_dir = temp_dir / "data"
    list_dir = data_dir / "lists"

    await aos.makedirs(ark_dir, exist_ok=True)
    await aos.makedirs(binary_dir, exist_ok=True)
    await aos.makedirs(list_dir, exist_ok=True)
    await touch_file(list_dir / "PlayersExclusiveJoinList.txt")
    await touch_file(list_dir / "PlayersJoinNoCheckList.txt")

    for map_name in ["BobsMissions_WP", "TheIsland_WP"]:
        map_dir = data_dir / "maps" / map_name
        mod_dir = map_dir / "mods"
        saved_dir = map_dir / "saved"
        compatdata_dir = map_dir / "compatdata"
        config_dir = saved_dir / "Config" / "WindowsServer"
        log_dir = saved_dir / "Logs"

        await aos.makedirs(mod_dir, exist_ok=True)
        await aos.makedirs(saved_dir, exist_ok=True)
        await aos.makedirs(compatdata_dir, exist_ok=True)
        await aos.makedirs(config_dir, exist_ok=True)
        await aos.makedirs(log_dir, exist_ok=True)

    with patch("ark_operator.ark.runner.run_async") as mock_run:
        yield _RunFixture(temp_dir, mock_run)


@pytest_asyncio.fixture(name="run")
async def run_fixture(run_failure: _RunFixture) -> AsyncGenerator[_RunFixture]:
    """Fake a run for ASA server."""

    async def _run(cmd: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401,ARG001
        map_name = "TheIsland_WP"
        if "BobsMissions_WP" in cmd:
            map_name = "BobsMissions_WP"

        await _write_log(
            run_failure.base_dir, "has successfully started", map_name=map_name
        )

    run_failure.mock_run.side_effect = _run

    yield run_failure


@pytest.mark.timeout(timeout=10)
@pytest.mark.asyncio
async def test_runner(run: _RunFixture) -> None:
    """Test runner."""

    saved_dir = run.base_dir / "data" / "maps" / "TheIsland_WP" / "saved"
    compatdata_dir = run.base_dir / "data" / "maps" / "TheIsland_WP" / "compatdata"

    server = ArkServer(
        server_dir=run.base_dir / "ark",
        data_dir=run.base_dir / "data",
        map_name="TheIsland_WP",
        session_name="Test",
        rcon_port=27020,
        rcon_password="password",
        game_port=7777,
        max_players=10,
        cluster_id="ark-cluster",
        battleye=True,
        allowed_platforms=["ALL"],
        whitelist=False,
        multihome_ip=None,
        parameters=[],
        options=[],
        mods=[],
    )

    await server.run()

    run.mock_run.assert_awaited_once_with(
        f'{run.base_dir!s}/ark/steam/.steam/root/compatibilitytools.d/GE-Proton9-22/proton run {run.base_dir!s}/ark/ark/ShooterGame/Binaries/Win64/ArkAscendedServer.exe TheIsland_WP?SessionName="Test"?RCONEnabled=True?RCONPort=27020?ServerAdminPassword=password -port=7777 -WinLiveMaxPlayers=10 -clusterid=ark-cluster -ClusterDirOverride={run.base_dir!s}/data -NoTransferFromFiltering -ServerPlatform=ALL',
        dry_run=False,
        env={
            "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(compatdata_dir),
            "STEAM_COMPAT_DATA_PATH": str(compatdata_dir),
        },
        echo=True,
    )

    assert await aos.path.exists(saved_dir / ".started") is True
    await _assert_file_contents(
        saved_dir / "Logs" / "ShooterGame.log", "has successfully started"
    )
    await _assert_config(
        run.base_dir,
        """[ServerSettings]
RCONEnabled = True
RCONPort = 27020
ServerAdminPassword = password

[SessionSettings]
Port = 7777
SessionName = Test

""",
    )


@pytest.mark.timeout(timeout=10)
@pytest.mark.asyncio
async def test_runner_no_startup(run_failure: _RunFixture) -> None:
    """Test runner."""

    saved_dir = run_failure.base_dir / "data" / "maps" / "TheIsland_WP" / "saved"
    compatdata_dir = (
        run_failure.base_dir / "data" / "maps" / "TheIsland_WP" / "compatdata"
    )

    server = ArkServer(
        server_dir=run_failure.base_dir / "ark",
        data_dir=run_failure.base_dir / "data",
        map_name="TheIsland_WP",
        session_name="Test",
        rcon_port=27020,
        rcon_password="password",
        game_port=7777,
        max_players=10,
        cluster_id="ark-cluster",
        battleye=True,
        allowed_platforms=["ALL"],
        whitelist=False,
        multihome_ip=None,
        parameters=[],
        options=[],
        mods=[],
    )

    await server.run()

    run_failure.mock_run.assert_awaited_once_with(
        f'{run_failure.base_dir!s}/ark/steam/.steam/root/compatibilitytools.d/GE-Proton9-22/proton run {run_failure.base_dir!s}/ark/ark/ShooterGame/Binaries/Win64/ArkAscendedServer.exe TheIsland_WP?SessionName="Test"?RCONEnabled=True?RCONPort=27020?ServerAdminPassword=password -port=7777 -WinLiveMaxPlayers=10 -clusterid=ark-cluster -ClusterDirOverride={run_failure.base_dir!s}/data -NoTransferFromFiltering -ServerPlatform=ALL',
        dry_run=False,
        env={
            "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(compatdata_dir),
            "STEAM_COMPAT_DATA_PATH": str(compatdata_dir),
        },
        echo=True,
    )

    assert await aos.path.exists(saved_dir / ".started") is False
    await _assert_file_contents(saved_dir / "Logs" / "ShooterGame.log", "")
    await _assert_config(
        run_failure.base_dir,
        """[ServerSettings]
RCONEnabled = True
RCONPort = 27020
ServerAdminPassword = password

[SessionSettings]
Port = 7777
SessionName = Test

""",
    )


@pytest.mark.timeout(timeout=10)
@pytest.mark.asyncio
async def test_runner_existing_log(run: _RunFixture) -> None:
    """Test runner."""

    saved_dir = run.base_dir / "data" / "maps" / "TheIsland_WP" / "saved"
    compatdata_dir = run.base_dir / "data" / "maps" / "TheIsland_WP" / "compatdata"

    async with aopen(saved_dir / ".started", "w") as f:
        await f.write("testing test")

    async with aopen(saved_dir / "Logs" / "ShooterGame.log", "w") as f:
        await f.write("testing test")

    server = ArkServer(
        server_dir=run.base_dir / "ark",
        data_dir=run.base_dir / "data",
        map_name="TheIsland_WP",
        session_name="Test",
        rcon_port=27020,
        rcon_password="password",
        game_port=7777,
        max_players=10,
        cluster_id="ark-cluster",
        battleye=True,
        allowed_platforms=["ALL"],
        whitelist=False,
        multihome_ip=None,
        parameters=[],
        options=[],
        mods=[],
    )

    await server.run()

    run.mock_run.assert_awaited_once_with(
        f'{run.base_dir!s}/ark/steam/.steam/root/compatibilitytools.d/GE-Proton9-22/proton run {run.base_dir!s}/ark/ark/ShooterGame/Binaries/Win64/ArkAscendedServer.exe TheIsland_WP?SessionName="Test"?RCONEnabled=True?RCONPort=27020?ServerAdminPassword=password -port=7777 -WinLiveMaxPlayers=10 -clusterid=ark-cluster -ClusterDirOverride={run.base_dir!s}/data -NoTransferFromFiltering -ServerPlatform=ALL',
        dry_run=False,
        env={
            "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(compatdata_dir),
            "STEAM_COMPAT_DATA_PATH": str(compatdata_dir),
        },
        echo=True,
    )

    assert await aos.path.exists(saved_dir / ".started") is True
    await _assert_file_contents(saved_dir / ".started", "")
    await _assert_file_contents(
        saved_dir / "Logs" / "ShooterGame.log", "has successfully started"
    )
    await _assert_config(
        run.base_dir,
        """[ServerSettings]
RCONEnabled = True
RCONPort = 27020
ServerAdminPassword = password

[SessionSettings]
Port = 7777
SessionName = Test

""",
    )


@pytest.mark.timeout(timeout=10)
@pytest.mark.asyncio
async def test_runner_extra_args(run: _RunFixture) -> None:
    """Test runner."""

    saved_dir = run.base_dir / "data" / "maps" / "BobsMissions_WP" / "saved"
    compatdata_dir = run.base_dir / "data" / "maps" / "BobsMissions_WP" / "compatdata"

    server = ArkServer(
        server_dir=run.base_dir / "ark",
        data_dir=run.base_dir / "data",
        map_name="BobsMissions_WP",
        session_name="Test",
        rcon_port=27020,
        rcon_password="password",
        game_port=7777,
        max_players=10,
        cluster_id="ark-cluster",
        battleye=False,
        allowed_platforms=["XSX", "PS5"],
        whitelist=True,
        multihome_ip="127.0.0.1",
        parameters=[],
        options=[],
        mods=[],
    )

    await server.run()

    run.mock_run.assert_awaited_once_with(
        f'{run.base_dir!s}/ark/steam/.steam/root/compatibilitytools.d/GE-Proton9-22/proton run {run.base_dir!s}/ark/ark/ShooterGame/Binaries/Win64/ArkAscendedServer.exe BobsMissions_WP?SessionName="Test"?RCONEnabled=True?RCONPort=27020?ServerAdminPassword=password -port=7777 -WinLiveMaxPlayers=10 -clusterid=ark-cluster -ClusterDirOverride={run.base_dir!s}/data -NoTransferFromFiltering -ServerPlatform=PS5+XSX -NoBattlEye -exclusivejoin -MULTIHOME -mods=1005639',
        dry_run=False,
        env={
            "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(compatdata_dir),
            "STEAM_COMPAT_DATA_PATH": str(compatdata_dir),
        },
        echo=True,
    )

    assert await aos.path.exists(saved_dir / ".started") is True
    await _assert_file_contents(
        saved_dir / "Logs" / "ShooterGame.log", "has successfully started"
    )
    await _assert_config(
        run.base_dir,
        """[ServerSettings]
RCONEnabled = True
RCONPort = 27020
ServerAdminPassword = password

[SessionSettings]
Port = 7777
SessionName = Test
MultiHome = 127.0.0.1

[MultiHome]
Multihome = True

""",
        map_name="BobsMissions_WP",
    )


@pytest.mark.timeout(timeout=10)
@pytest.mark.asyncio
async def test_runner_user_opts(run: _RunFixture) -> None:
    """Test runner."""

    saved_dir = run.base_dir / "data" / "maps" / "TheIsland_WP" / "saved"
    compatdata_dir = run.base_dir / "data" / "maps" / "TheIsland_WP" / "compatdata"

    server = ArkServer(
        server_dir=run.base_dir / "ark",
        data_dir=run.base_dir / "data",
        map_name="TheIsland_WP",
        session_name="Test",
        rcon_port=27020,
        rcon_password="password",
        game_port=7777,
        max_players=10,
        cluster_id="ark-cluster",
        battleye=True,
        allowed_platforms=["ALL"],
        whitelist=False,
        multihome_ip=None,
        parameters=["AlwaysTickDedicatedSkeletalMeshes", "AllowCaveBuildingPvE"],
        options=["NoDinos", "MaxNumOfSaveBackups=3"],
        mods=["927090", "928548"],
    )

    await server.run()

    run.mock_run.assert_awaited_once_with(
        f'{run.base_dir!s}/ark/steam/.steam/root/compatibilitytools.d/GE-Proton9-22/proton run {run.base_dir!s}/ark/ark/ShooterGame/Binaries/Win64/ArkAscendedServer.exe TheIsland_WP?SessionName="Test"?RCONEnabled=True?RCONPort=27020?AlwaysTickDedicatedSkeletalMeshes?AllowCaveBuildingPvE?ServerAdminPassword=password -port=7777 -WinLiveMaxPlayers=10 -clusterid=ark-cluster -ClusterDirOverride={run.base_dir!s}/data -NoTransferFromFiltering -ServerPlatform=ALL -NoDinos -MaxNumOfSaveBackups=3 -mods=927090,928548',
        dry_run=False,
        env={
            "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(compatdata_dir),
            "STEAM_COMPAT_DATA_PATH": str(compatdata_dir),
        },
        echo=True,
    )

    assert await aos.path.exists(saved_dir / ".started") is True
    await _assert_file_contents(
        saved_dir / "Logs" / "ShooterGame.log", "has successfully started"
    )
    await _assert_config(
        run.base_dir,
        """[ServerSettings]
RCONEnabled = True
RCONPort = 27020
ServerAdminPassword = password

[SessionSettings]
Port = 7777
SessionName = Test

""",
    )


@pytest.mark.timeout(timeout=10)
@pytest.mark.asyncio
async def test_runner_managed_param(run: _RunFixture) -> None:
    """Test runner."""

    server = ArkServer(
        server_dir=run.base_dir / "ark",
        data_dir=run.base_dir / "data",
        map_name="TheIsland_WP",
        session_name="Test",
        rcon_port=27020,
        rcon_password="password",
        game_port=7777,
        max_players=10,
        cluster_id="ark-cluster",
        battleye=True,
        allowed_platforms=["ALL"],
        whitelist=False,
        multihome_ip=None,
        parameters=["RCONEnabled=False"],
        options=[],
        mods=[],
    )

    with pytest.raises(ValueError, match="they cannot be proved manually"):
        await server.run()

    run.mock_run.assert_not_awaited()


@pytest.mark.timeout(timeout=10)
@pytest.mark.asyncio
async def test_runner_managed_opt(run: _RunFixture) -> None:
    """Test runner."""

    server = ArkServer(
        server_dir=run.base_dir / "ark",
        data_dir=run.base_dir / "data",
        map_name="TheIsland_WP",
        session_name="Test",
        rcon_port=27020,
        rcon_password="password",
        game_port=7777,
        max_players=10,
        cluster_id="ark-cluster",
        battleye=True,
        allowed_platforms=["ALL"],
        whitelist=False,
        multihome_ip=None,
        parameters=[],
        options=["clusterid=test"],
        mods=[],
        global_config=run.base_dir / "globalgus.ini",
        map_config=run.base_dir / "mapgus.ini",
    )

    with pytest.raises(ValueError, match="they cannot be proved manually"):
        await server.run()

    run.mock_run.assert_not_awaited()


@pytest.mark.timeout(timeout=10)
@pytest.mark.asyncio
async def test_runner_global_gus(run: _RunFixture) -> None:
    """Test runner."""

    saved_dir = run.base_dir / "data" / "maps" / "TheIsland_WP" / "saved"
    compatdata_dir = run.base_dir / "data" / "maps" / "TheIsland_WP" / "compatdata"

    async with aopen(run.base_dir / "globalgus.ini", "w") as f:
        await f.write("""[ServerSettings]
ServerPVE = True
RCONEnabled = False""")

    server = ArkServer(
        server_dir=run.base_dir / "ark",
        data_dir=run.base_dir / "data",
        map_name="TheIsland_WP",
        session_name="Test",
        rcon_port=27020,
        rcon_password="password",
        game_port=7777,
        max_players=10,
        cluster_id="ark-cluster",
        battleye=True,
        allowed_platforms=["ALL"],
        whitelist=False,
        multihome_ip=None,
        parameters=[],
        options=[],
        mods=[],
        global_config=run.base_dir / "globalgus.ini",
    )

    await server.run()

    run.mock_run.assert_awaited_once_with(
        f'{run.base_dir!s}/ark/steam/.steam/root/compatibilitytools.d/GE-Proton9-22/proton run {run.base_dir!s}/ark/ark/ShooterGame/Binaries/Win64/ArkAscendedServer.exe TheIsland_WP?SessionName="Test"?RCONEnabled=True?RCONPort=27020?ServerAdminPassword=password -port=7777 -WinLiveMaxPlayers=10 -clusterid=ark-cluster -ClusterDirOverride={run.base_dir!s}/data -NoTransferFromFiltering -ServerPlatform=ALL',
        dry_run=False,
        env={
            "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(compatdata_dir),
            "STEAM_COMPAT_DATA_PATH": str(compatdata_dir),
        },
        echo=True,
    )

    assert await aos.path.exists(saved_dir / ".started") is True
    await _assert_file_contents(
        saved_dir / "Logs" / "ShooterGame.log", "has successfully started"
    )
    await _assert_config(
        run.base_dir,
        """[ServerSettings]
ServerPVE = True
RCONEnabled = True
RCONPort = 27020
ServerAdminPassword = password

[SessionSettings]
Port = 7777
SessionName = Test

""",
    )


@pytest.mark.timeout(timeout=10)
@pytest.mark.asyncio
async def test_runner_map_gus(run: _RunFixture) -> None:
    """Test runner."""

    saved_dir = run.base_dir / "data" / "maps" / "TheIsland_WP" / "saved"
    compatdata_dir = run.base_dir / "data" / "maps" / "TheIsland_WP" / "compatdata"

    async with aopen(run.base_dir / "mapgus.ini", "w") as f:
        await f.write("""[ServerSettings]
ServerPVE = True
RCONEnabled = False""")

    server = ArkServer(
        server_dir=run.base_dir / "ark",
        data_dir=run.base_dir / "data",
        map_name="TheIsland_WP",
        session_name="Test",
        rcon_port=27020,
        rcon_password="password",
        game_port=7777,
        max_players=10,
        cluster_id="ark-cluster",
        battleye=True,
        allowed_platforms=["ALL"],
        whitelist=False,
        multihome_ip=None,
        parameters=[],
        options=[],
        mods=[],
        global_config=run.base_dir / "globalgus.ini",
        map_config=run.base_dir / "mapgus.ini",
    )

    await server.run()

    run.mock_run.assert_awaited_once_with(
        f'{run.base_dir!s}/ark/steam/.steam/root/compatibilitytools.d/GE-Proton9-22/proton run {run.base_dir!s}/ark/ark/ShooterGame/Binaries/Win64/ArkAscendedServer.exe TheIsland_WP?SessionName="Test"?RCONEnabled=True?RCONPort=27020?ServerAdminPassword=password -port=7777 -WinLiveMaxPlayers=10 -clusterid=ark-cluster -ClusterDirOverride={run.base_dir!s}/data -NoTransferFromFiltering -ServerPlatform=ALL',
        dry_run=False,
        env={
            "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(compatdata_dir),
            "STEAM_COMPAT_DATA_PATH": str(compatdata_dir),
        },
        echo=True,
    )

    assert await aos.path.exists(saved_dir / ".started") is True
    await _assert_file_contents(
        saved_dir / "Logs" / "ShooterGame.log", "has successfully started"
    )
    await _assert_config(
        run.base_dir,
        """[ServerSettings]
ServerPVE = True
RCONEnabled = True
RCONPort = 27020
ServerAdminPassword = password

[SessionSettings]
Port = 7777
SessionName = Test

""",
    )


@pytest.mark.timeout(timeout=10)
@pytest.mark.asyncio
async def test_runner_gus(run: _RunFixture) -> None:
    """Test runner."""

    saved_dir = run.base_dir / "data" / "maps" / "TheIsland_WP" / "saved"
    compatdata_dir = run.base_dir / "data" / "maps" / "TheIsland_WP" / "compatdata"

    async with aopen(run.base_dir / "globalgus.ini", "w") as f:
        await f.write("""[ServerSettings]
ServerPVE = False
RCONPort = 27777
RCONServerGameLogBuffer = 600""")

    async with aopen(run.base_dir / "mapgus.ini", "w") as f:
        await f.write("""[ServerSettings]
ServerPVE = True
RCONPort = 27778""")

    server = ArkServer(
        server_dir=run.base_dir / "ark",
        data_dir=run.base_dir / "data",
        map_name="TheIsland_WP",
        session_name="Test",
        rcon_port=27020,
        rcon_password="password",
        game_port=7777,
        max_players=10,
        cluster_id="ark-cluster",
        battleye=True,
        allowed_platforms=["ALL"],
        whitelist=False,
        multihome_ip=None,
        parameters=[],
        options=[],
        mods=[],
        global_config=run.base_dir / "globalgus.ini",
        map_config=run.base_dir / "mapgus.ini",
    )

    await server.run()

    run.mock_run.assert_awaited_once_with(
        f'{run.base_dir!s}/ark/steam/.steam/root/compatibilitytools.d/GE-Proton9-22/proton run {run.base_dir!s}/ark/ark/ShooterGame/Binaries/Win64/ArkAscendedServer.exe TheIsland_WP?SessionName="Test"?RCONEnabled=True?RCONPort=27020?ServerAdminPassword=password -port=7777 -WinLiveMaxPlayers=10 -clusterid=ark-cluster -ClusterDirOverride={run.base_dir!s}/data -NoTransferFromFiltering -ServerPlatform=ALL',
        dry_run=False,
        env={
            "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(compatdata_dir),
            "STEAM_COMPAT_DATA_PATH": str(compatdata_dir),
        },
        echo=True,
    )

    assert await aos.path.exists(saved_dir / ".started") is True
    await _assert_file_contents(
        saved_dir / "Logs" / "ShooterGame.log", "has successfully started"
    )
    await _assert_config(
        run.base_dir,
        """[ServerSettings]
ServerPVE = True
RCONPort = 27020
RCONServerGameLogBuffer = 600
RCONEnabled = True
ServerAdminPassword = password

[SessionSettings]
Port = 7777
SessionName = Test

""",
    )
