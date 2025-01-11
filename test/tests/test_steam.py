"""Test Steam utils."""

import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from unittest.mock import AsyncMock, Mock, call, patch

import pytest
import pytest_asyncio
from aiofiles import open as aopen
from aiofiles import os as aos
from aiofiles.tempfile import TemporaryDirectory
from pytest_httpx import HTTPXMock

from ark_operator.data import ArkClusterSpec
from ark_operator.exceptions import SteamCMDError
from ark_operator.steam import PROTON_VERSION, Steam, install_proton, install_steamcmd
from tests.conftest import BASE_DIR

TEST_ARCHIVE: dict[str, bytes] = {}

with (BASE_DIR / "test" / "archive.zip").open("rb") as f:
    TEST_ARCHIVE["Windows"] = f.read()

with (BASE_DIR / "test" / "archive.tar.gz").open("rb") as f:
    TEST_ARCHIVE["Linux"] = f.read()


@pytest_asyncio.fixture(name="steamcmd_path")
async def steamcmd_path_fixture() -> AsyncGenerator[Path]:
    """Steamcmd installed fixture."""

    async with TemporaryDirectory() as path:
        yield Path(path) / "steam"


@pytest.fixture(name="steam")
def steam_fixture(steamcmd_path: Path) -> Steam:
    """Steam fixture."""

    return Steam(steamcmd_path)


@pytest_asyncio.fixture(name="steamcmd_installed")
async def steamcmd_installed_fixture(
    steamcmd_path: Path,
) -> AsyncGenerator[Path]:
    """Steamcmd installed fixture."""

    steamcmd_path.mkdir(parents=True, exist_ok=True)
    exe = steamcmd_path / "steamcmd.exe"
    sh = steamcmd_path / "steamcmd.sh"
    async with aopen(exe, "wb") as f:
        await f.write(b"")
    async with aopen(sh, "wb") as f:
        await f.write(b"")

    yield steamcmd_path


@pytest_asyncio.fixture(name="proton_installed")
async def proton_installed_fixture(
    steamcmd_path: Path,
) -> AsyncGenerator[Path]:
    """proton installed fixture."""

    proton_dir = (
        steamcmd_path
        / ".steam"
        / "root"
        / "compatibilitytools.d"
        / f"GE-Proton{PROTON_VERSION}"
    )
    proton_dir.mkdir(parents=True, exist_ok=True)
    exe = proton_dir / "proton"
    async with aopen(exe, "wb") as f:
        await f.write(b"")

    yield steamcmd_path


@patch("ark_operator.steam.CDNClient")
@patch("ark_operator.steam.SteamClient")
def test_initialize(mock_steam: Mock, mock_cdn: Mock, steam: Steam) -> None:
    """Test SteamClient and CDNClient are initialized correctly."""

    mock_client = Mock()
    mock_steam.return_value = mock_client

    steam.cdn  # noqa: B018

    mock_steam.assert_called_once()
    mock_client.anonymous_login.assert_called_once()
    mock_cdn.assert_called_once()


@patch("ark_operator.steam.install_proton")
@patch("ark_operator.steam.steamcmd_run")
@pytest.mark.asyncio
async def test_install_ark(
    mock_steamcmd: AsyncMock,
    mock_proton: AsyncMock,
    steam: Steam,
) -> None:
    """Test install_ark."""

    await steam.install_ark(Path("/test"))

    mock_steamcmd.assert_awaited_once_with(
        "+@ShutdownOnFailedCommand 1 +@NoPromptForPassword 1 +@sSteamCmdForcePlatformType windows +force_install_dir /test +login anonymous +app_update 2430930 validate +quit",
        install_dir=steam.install_dir,
        retries=3,
        dry_run=False,
    )
    mock_proton.assert_awaited_once_with(steam.install_dir, dry_run=False)


@patch("ark_operator.steam.install_proton")
@patch("ark_operator.steam.steamcmd_run")
@pytest.mark.asyncio
async def test_install_ark_dry_run(
    mock_steamcmd: AsyncMock, mock_proton: AsyncMock, steam: Steam
) -> None:
    """Test install_ark."""

    await steam.install_ark(Path("/test"), dry_run=True)

    mock_steamcmd.assert_awaited_once_with(
        "+@ShutdownOnFailedCommand 1 +@NoPromptForPassword 1 +@sSteamCmdForcePlatformType windows +force_install_dir /test +login anonymous +app_update 2430930 validate +quit",
        install_dir=steam.install_dir,
        retries=3,
        dry_run=True,
    )
    mock_proton.assert_awaited_once_with(steam.install_dir, dry_run=True)


@patch("ark_operator.steam.install_proton")
@patch("ark_operator.steam.steamcmd_run")
@pytest.mark.asyncio
async def test_install_ark_no_validate(
    mock_steamcmd: AsyncMock, mock_proton: AsyncMock, steam: Steam
) -> None:
    """Test install_ark."""

    await steam.install_ark(Path("/test"), validate=False)

    mock_steamcmd.assert_awaited_once_with(
        "+@ShutdownOnFailedCommand 1 +@NoPromptForPassword 1 +@sSteamCmdForcePlatformType windows +force_install_dir /test +login anonymous +app_update 2430930 +quit",
        install_dir=steam.install_dir,
        retries=3,
        dry_run=False,
    )
    mock_proton.assert_awaited_once_with(steam.install_dir, dry_run=False)


@patch("ark_operator.steam.copy_ark")
@pytest.mark.asyncio
async def test_copy_ark(mock_copy: AsyncMock, steam: Steam) -> None:
    """Test Steam.copy_ark calls ark.utils."""

    await steam.copy_ark(Path("/test"), Path("/test2"))

    mock_copy.assert_awaited_once_with(Path("/test"), Path("/test2"), dry_run=False)


@patch("ark_operator.steam.copy_ark")
@pytest.mark.asyncio
async def test_copy_ark_dry_run(mock_copy: AsyncMock, steam: Steam) -> None:
    """Test Steam.copy_ark calls ark.utils."""

    await steam.copy_ark(Path("/test"), Path("/test2"), dry_run=True)

    mock_copy.assert_awaited_once_with(Path("/test"), Path("/test2"), dry_run=True)


@patch("ark_operator.steam.has_newer_version")
@pytest.mark.asyncio
async def test_has_newer_version(mock_version: AsyncMock, steam: Steam) -> None:
    """Test Steam.has_newer_version calls ark.utils."""

    await steam.has_newer_version(Path("/test"))

    mock_version.assert_awaited_once_with(steam, Path("/test"))


@patch("ark_operator.steam.run_async")
@patch("ark_operator.steam.install_steamcmd")
@pytest.mark.asyncio
async def test_steamcmd_run(
    mock_install: AsyncMock, mock_run: AsyncMock, steam: Steam
) -> None:
    """Test steamcmd_run."""

    mock_install.return_value = Path("/test/steamcmd")

    await steam.cmd("test")

    mock_install.assert_awaited_once_with(steam.install_dir, force=False, dry_run=False)
    mock_run.assert_awaited_once_with(
        "/test/steamcmd test",
        check=True,
        output_level=logging.INFO,
        dry_run=False,
        env={"HOME": str(steam.install_dir)},
    )


@patch("ark_operator.steam.run_async")
@patch("ark_operator.steam.install_steamcmd")
@pytest.mark.asyncio
async def test_steamcmd_run_dry_run(
    mock_install: AsyncMock, mock_run: AsyncMock, steam: Steam
) -> None:
    """Test steamcmd_run."""

    mock_install.return_value = Path("/test/steamcmd")

    await steam.cmd("test", dry_run=True)

    mock_install.assert_awaited_once_with(steam.install_dir, force=False, dry_run=True)
    mock_run.assert_awaited_once_with(
        "/test/steamcmd test",
        check=True,
        output_level=logging.INFO,
        dry_run=True,
        env={"HOME": str(steam.install_dir)},
    )


@patch("ark_operator.steam.run_async")
@patch("ark_operator.steam.install_steamcmd")
@pytest.mark.asyncio
async def test_steamcmd_run_retry(
    mock_install: AsyncMock, mock_run: AsyncMock, steam: Steam
) -> None:
    """Test steamcmd_run."""

    mock_install.return_value = Path("/test/steamcmd")
    mock_run.side_effect = [
        CalledProcessError(1, "/test/steamcmd test"),
        CompletedProcess(["/test/steamcmd", "test"], 0),
    ]

    await steam.cmd("test", force_download=True)

    mock_install.assert_awaited_once_with(steam.install_dir, force=True, dry_run=False)
    mock_run.assert_has_awaits(
        [
            call(
                "/test/steamcmd test",
                check=True,
                output_level=logging.INFO,
                dry_run=False,
                env={"HOME": str(steam.install_dir)},
            ),
            call(
                "/test/steamcmd test",
                check=True,
                output_level=logging.INFO,
                dry_run=False,
                env={"HOME": str(steam.install_dir)},
            ),
        ]
    )


@patch("ark_operator.steam.run_async")
@patch("ark_operator.steam.install_steamcmd")
@pytest.mark.asyncio
async def test_steamcmd_run_error(
    mock_install: AsyncMock, mock_run: AsyncMock, steam: Steam
) -> None:
    """Test steamcmd_run."""

    mock_install.return_value = Path("/test/steamcmd")
    mock_run.side_effect = CalledProcessError(1, "/test/steamcmd test")

    with pytest.raises(SteamCMDError):
        await steam.cmd("test", retries=0)

    mock_install.assert_awaited_once_with(steam.install_dir, force=False, dry_run=False)
    mock_run.assert_awaited_once_with(
        "/test/steamcmd test",
        check=True,
        output_level=logging.INFO,
        dry_run=False,
        env={"HOME": str(steam.install_dir)},
    )


@patch("ark_operator.steam.platform")
@pytest.mark.asyncio
async def test_install_steamcmd_bad_platform(
    mock_platform: AsyncMock, httpx_mock: HTTPXMock
) -> None:
    """Test install_steamcmd."""

    mock_platform.system.return_value = "Darwin"

    with pytest.raises(SteamCMDError):
        await install_steamcmd(Path("/test/steamcmd"))

    assert len(httpx_mock.get_requests()) == 0


@patch("ark_operator.steam.aos")
@patch("ark_operator.steam.platform")
@pytest.mark.asyncio
async def test_install_steamcmd_already_installed(
    mock_platform: AsyncMock, mock_aos: Mock, httpx_mock: HTTPXMock
) -> None:
    """Test install_steamcmd."""

    mock_platform.system.return_value = "Linux"
    mock_aos.path.exists = AsyncMock(return_value=True)

    await install_steamcmd(Path("/test/steamcmd"))

    mock_aos.path.exists.assert_awaited_once()
    assert len(httpx_mock.get_requests()) == 0


@patch("ark_operator.steam._extract_archive", AsyncMock())
@patch("ark_operator.steam.platform")
@pytest.mark.asyncio
async def test_install_steamcmd_extract_failed(
    mock_platform: AsyncMock,
    httpx_mock: HTTPXMock,
    steamcmd_path: Path,
) -> None:
    """Test install_steamcmd."""

    httpx_mock.add_response(status_code=200, content=TEST_ARCHIVE["Linux"])

    mock_platform.system.return_value = "Linux"

    with pytest.raises(SteamCMDError):
        assert await install_steamcmd(steamcmd_path)

    assert len(httpx_mock.get_requests()) == 1


@patch("ark_operator.steam._extract_archive", AsyncMock())
@patch("ark_operator.steam.platform")
@pytest.mark.asyncio
async def test_install_steamcmd_download_failed(
    mock_platform: AsyncMock,
    httpx_mock: HTTPXMock,
    steamcmd_path: Path,
) -> None:
    """Test install_steamcmd."""

    httpx_mock.add_response(status_code=400)

    mock_platform.system.return_value = "Linux"

    with pytest.raises(SteamCMDError):
        assert await install_steamcmd(steamcmd_path)

    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.parametrize(
    ("platform", "ext"),
    [
        ("Linux", "sh"),
        ("Windows", "exe"),
    ],
)
@patch("ark_operator.steam.platform")
@pytest.mark.asyncio
async def test_install_steamcmd(
    mock_platform: AsyncMock,
    httpx_mock: HTTPXMock,
    steamcmd_path: Path,
    platform: str,
    ext: str,
) -> None:
    """Test install_steamcmd."""

    httpx_mock.add_response(status_code=200, content=TEST_ARCHIVE[platform])

    mock_platform.system.return_value = platform

    assert await install_steamcmd(steamcmd_path) == steamcmd_path / f"steamcmd.{ext}"
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.parametrize(
    ("platform", "ext"),
    [
        ("Linux", "sh"),
        ("Windows", "exe"),
    ],
)
@patch("ark_operator.steam.platform")
@pytest.mark.asyncio
async def test_install_steamcmd_reinstall(
    mock_platform: AsyncMock,
    httpx_mock: HTTPXMock,
    steamcmd_installed: Path,
    platform: str,
    ext: str,
) -> None:
    """Test install_steamcmd."""

    httpx_mock.add_response(status_code=200, content=TEST_ARCHIVE[platform])

    mock_platform.system.return_value = platform

    path = await install_steamcmd(steamcmd_installed, force=True)
    assert path == steamcmd_installed / f"steamcmd.{ext}"
    assert len(httpx_mock.get_requests()) == 1


@patch("ark_operator.steam.aioshutil")
@patch("ark_operator.steam.platform")
@pytest.mark.asyncio
async def test_install_steamcmd_reinstall_dry_run(
    mock_platform: AsyncMock,
    mock_shutil: Mock,
    httpx_mock: HTTPXMock,
    steamcmd_installed: Path,
) -> None:
    """Test install_steamcmd."""

    mock_shutil.rmtree = AsyncMock()
    mock_platform.system.return_value = "Linux"

    path = await install_steamcmd(steamcmd_installed, force=True, dry_run=True)
    assert path == steamcmd_installed / "steamcmd.sh"
    assert len(httpx_mock.get_requests()) == 0
    mock_shutil.rmtree.assert_not_awaited()


@patch("ark_operator.steam.install_proton")
@patch("ark_operator.steam.steamcmd_run")
@patch("ark_operator.steam.install_steamcmd")
@patch("ark_operator.steam.copy_ark")
@pytest.mark.asyncio
async def test_init_volumes(  # noqa: PLR0913
    mock_copy: AsyncMock,
    mock_steamcmd: AsyncMock,
    mock_run: AsyncMock,
    mock_proton: AsyncMock,
    steam: Steam,
    steamcmd_path: Path,
) -> None:
    """Test init_volumes."""

    base_dir = steamcmd_path.parent
    spec = ArkClusterSpec()
    await steam.init_volumes(steamcmd_path.parent, spec=spec)

    assert await aos.path.exists(base_dir / "data" / "clusters" / "ark-cluster") is True
    assert await aos.path.exists(base_dir / "data" / "maps") is True
    list_dir = base_dir / "data" / "lists"
    assert await aos.path.exists(list_dir) is True
    assert await aos.path.exists(list_dir / "PlayersExclusiveJoinList.txt") is True
    assert await aos.path.exists(list_dir / "PlayersJoinNoCheckList.txt") is True

    for map_name in spec.server.all_maps:
        assert (
            await aos.path.exists(
                base_dir
                / "data"
                / "maps"
                / map_name
                / "saved"
                / "Config"
                / "WindowsServer"
            )
            is True
        )
        assert (
            await aos.path.exists(base_dir / "data" / "maps" / map_name / "mods")
            is True
        )

    assert await aos.path.exists(base_dir / "server-a" / "steam") is True
    assert await aos.path.exists(base_dir / "server-b" / "steam") is True
    assert await aos.path.exists(base_dir / "server-a" / "ark") is True
    assert await aos.path.exists(base_dir / "server-b" / "ark") is True

    mock_run.assert_awaited_once()
    mock_proton.assert_awaited_once_with(base_dir / "server-a" / "steam", dry_run=False)
    mock_steamcmd.assert_awaited_once_with(
        base_dir / "server-b" / "steam", dry_run=False
    )
    mock_copy.assert_awaited_once_with(
        base_dir / "server-a" / "ark", base_dir / "server-b" / "ark", dry_run=False
    )


@patch("ark_operator.steam.aos")
@patch("ark_operator.steam.install_proton")
@patch("ark_operator.steam.steamcmd_run")
@patch("ark_operator.steam.install_steamcmd")
@patch("ark_operator.steam.copy_ark")
@pytest.mark.asyncio
async def test_init_volumes_dry_run(  # noqa: PLR0913
    mock_copy: AsyncMock,
    mock_steamcmd: AsyncMock,
    mock_run: AsyncMock,
    mock_proton: AsyncMock,
    mock_aos: Mock,
    steam: Steam,
    steamcmd_path: Path,
) -> None:
    """Test init_volumes."""

    mock_aos.makedirs = AsyncMock()

    base_dir = steamcmd_path.parent
    spec = ArkClusterSpec()
    await steam.init_volumes(steamcmd_path.parent, spec=spec, dry_run=True)

    mock_proton.assert_awaited_once_with(base_dir / "server-a" / "steam", dry_run=True)
    mock_aos.makedirs.assert_not_awaited()
    mock_run.assert_awaited_once()
    mock_steamcmd.assert_awaited_once_with(
        base_dir / "server-b" / "steam", dry_run=True
    )
    mock_copy.assert_awaited_once_with(
        base_dir / "server-a" / "ark", base_dir / "server-b" / "ark", dry_run=True
    )


@patch("ark_operator.steam.aos")
@pytest.mark.asyncio
async def test_install_proton_already_installed(
    mock_aos: Mock, httpx_mock: HTTPXMock
) -> None:
    """Test install_proton."""

    mock_aos.path.exists = AsyncMock(return_value=True)

    await install_proton(Path("/test/proton"))

    mock_aos.path.exists.assert_awaited_once()
    assert len(httpx_mock.get_requests()) == 0


@patch("ark_operator.steam._extract_archive", AsyncMock())
@pytest.mark.asyncio
async def test_install_proton_extract_failed(
    httpx_mock: HTTPXMock,
    steamcmd_path: Path,
) -> None:
    """Test install_proton."""

    httpx_mock.add_response(status_code=200, content=TEST_ARCHIVE["Linux"])

    with pytest.raises(SteamCMDError):
        assert await install_proton(steamcmd_path)

    assert len(httpx_mock.get_requests()) == 1


@patch("ark_operator.steam._extract_archive", AsyncMock())
@pytest.mark.asyncio
async def test_install_proton_download_failed(
    httpx_mock: HTTPXMock,
    steamcmd_path: Path,
) -> None:
    """Test install_proton."""

    httpx_mock.add_response(status_code=400)

    with pytest.raises(SteamCMDError):
        assert await install_proton(steamcmd_path)

    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
async def test_install_proton(
    httpx_mock: HTTPXMock,
    steamcmd_path: Path,
) -> None:
    """Test install_proton."""

    httpx_mock.add_response(status_code=200, content=TEST_ARCHIVE["Linux"])

    assert (
        await install_proton(steamcmd_path)
        == steamcmd_path
        / ".steam"
        / "root"
        / "compatibilitytools.d"
        / f"GE-Proton{PROTON_VERSION}"
        / "proton"
    )
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
async def test_install_proton_reinstall(
    httpx_mock: HTTPXMock,
    proton_installed: Path,
) -> None:
    """Test install_proton."""

    httpx_mock.add_response(status_code=200, content=TEST_ARCHIVE["Linux"])

    path = await install_proton(proton_installed, force=True)
    assert (
        path
        == proton_installed
        / ".steam"
        / "root"
        / "compatibilitytools.d"
        / f"GE-Proton{PROTON_VERSION}"
        / "proton"
    )
    assert len(httpx_mock.get_requests()) == 1


@patch("ark_operator.steam.aioshutil")
@pytest.mark.asyncio
async def test_install_proton_reinstall_dry_run(
    mock_shutil: Mock,
    httpx_mock: HTTPXMock,
    proton_installed: Path,
) -> None:
    """Test install_proton."""

    mock_shutil.rmtree = AsyncMock()

    path = await install_proton(proton_installed, force=True, dry_run=True)
    assert (
        path
        == proton_installed
        / ".steam"
        / "root"
        / "compatibilitytools.d"
        / f"GE-Proton{PROTON_VERSION}"
        / "proton"
    )
    assert len(httpx_mock.get_requests()) == 0
    mock_shutil.rmtree.assert_not_awaited()
