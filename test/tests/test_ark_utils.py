"""Placeholder tests."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ark_operator.ark_utils import (
    ARK_SERVER_APP_ID,
    copy_ark,
    get_ark_buildid,
    has_newer_version,
    install_ark,
    is_ark_newer,
)
from tests.conftest import BASE_DIR

TEST_ARK = BASE_DIR / "test" / "ark"


@patch("ark_operator.ark_utils.steamcmd_run")
@pytest.mark.asyncio
async def test_install_ark(mock_steam: AsyncMock) -> None:
    """Test install_ark."""

    await install_ark(Path("/test"), steam_dir=Path("/test2"))

    mock_steam.assert_awaited_once_with(
        "+@ShutdownOnFailedCommand 1 +@NoPromptForPassword 1 +@sSteamCmdForcePlatformType windows +force_install_dir /test +login anonymous +app_update 2430930 validate +quit",
        install_dir=Path("/test2"),
        retries=3,
    )


@patch("ark_operator.ark_utils.steamcmd_run")
@pytest.mark.asyncio
async def test_install_ark_no_validate(mock_steam: AsyncMock) -> None:
    """Test install_ark."""

    await install_ark(Path("/test"), steam_dir=Path("/test2"), validate=False)

    mock_steam.assert_awaited_once_with(
        "+@ShutdownOnFailedCommand 1 +@NoPromptForPassword 1 +@sSteamCmdForcePlatformType windows +force_install_dir /test +login anonymous +app_update 2430930 +quit",
        install_dir=Path("/test2"),
        retries=3,
    )


@pytest.mark.asyncio
async def test_get_ark_buildid() -> None:
    """Test get_ark_buildid."""

    assert await get_ark_buildid(TEST_ARK) == 16828472


@pytest.mark.asyncio
async def test_get_ark_buildid_src_missing() -> None:
    """Test get_ark_buildid if src ARK is missing."""

    assert await get_ark_buildid(Path("test")) is None


@pytest.mark.parametrize(
    ("buildid", "expected"), [(16828472, False), (16828470, False), (16828490, True)]
)
@pytest.mark.asyncio
async def test_has_newer_version(buildid: int, expected: bool) -> None:
    """Test has_newer_version."""

    steam = Mock()
    steam.cdn.get_app_depot_info.return_value = {
        "branches": {"public": {"buildid": buildid}}
    }

    assert await has_newer_version(steam, TEST_ARK) is expected
    steam.cdn.get_app_depot_info.assert_called_once_with(ARK_SERVER_APP_ID)


@pytest.mark.asyncio
async def test_has_newer_version_missing_src() -> None:
    """Test has_newer_version if src ARK is missing."""

    steam = Mock()
    assert await has_newer_version(steam, Path("/test")) is True
    steam.cdn.get_app_depot_info.assert_not_called()


@pytest.mark.parametrize(
    ("src_buildid", "dest_buildid", "expected", "calls"),
    [
        (16828472, 16828472, False, 2),
        (None, 16828472, False, 1),
        (16828472, None, True, 2),
        (16828482, 16828472, True, 2),
        (16828472, 16828482, False, 2),
    ],
)
@patch("ark_operator.ark_utils.get_ark_buildid")
@pytest.mark.asyncio
async def test_is_ark_newer(
    mock_buildid: Mock, src_buildid: int, dest_buildid: int, expected: bool, calls: int
) -> None:
    """Test is_ark_newer."""

    mock_buildid.side_effect = [src_buildid, dest_buildid]

    assert await is_ark_newer(Path("/test"), Path("/test2")) is expected
    assert mock_buildid.call_count == calls


@patch("ark_operator.ark_utils.aioshutil")
@patch("ark_operator.ark_utils.is_ark_newer")
@pytest.mark.asyncio
async def test_copy_ark_same(mock_is_new: Mock, mock_shutil: Mock) -> None:
    """Test copy_ark is ARK is not newer."""

    mock_shutil.rmtree = AsyncMock()
    mock_shutil.copytree = AsyncMock()
    mock_is_new.return_value = False

    await copy_ark(Path("/test"), Path("/test"))

    mock_shutil.rmtree.assert_not_awaited()
    mock_shutil.copytree.assert_not_awaited()


@patch("ark_operator.ark_utils.aioshutil")
@patch("ark_operator.ark_utils.is_ark_newer")
@pytest.mark.asyncio
async def test_copy_ark_not_newer(mock_is_new: Mock, mock_shutil: Mock) -> None:
    """Test copy_ark is ARK is not newer."""

    mock_shutil.rmtree = AsyncMock()
    mock_shutil.copytree = AsyncMock()
    mock_is_new.return_value = False

    await copy_ark(Path("/test"), TEST_ARK)

    mock_shutil.rmtree.assert_not_awaited()
    mock_shutil.copytree.assert_not_awaited()


@patch("ark_operator.ark_utils.aioshutil")
@patch("ark_operator.ark_utils.is_ark_newer")
@pytest.mark.asyncio
async def test_copy_ark_dest_exists(mock_is_new: Mock, mock_shutil: Mock) -> None:
    """Test copy_ark if dest ARK exists."""

    mock_shutil.rmtree = AsyncMock()
    mock_shutil.copytree = AsyncMock()
    mock_is_new.return_value = True

    await copy_ark(Path("/test"), TEST_ARK)

    mock_shutil.rmtree.assert_awaited_once()
    mock_shutil.copytree.assert_awaited_once()


@patch("ark_operator.ark_utils.aioshutil")
@patch("ark_operator.ark_utils.is_ark_newer")
@pytest.mark.asyncio
async def test_copy_ark_no_dest(mock_is_new: Mock, mock_shutil: Mock) -> None:
    """Test copy_ark if dest ARK does not exist."""

    mock_shutil.rmtree = AsyncMock()
    mock_shutil.copytree = AsyncMock()
    mock_is_new.return_value = True

    await copy_ark(Path("/test"), Path("/notarealpath"))

    mock_shutil.rmtree.assert_not_awaited()
    mock_shutil.copytree.assert_awaited_once()
