"""ARK helper functions."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import aioshutil
import vdf
from aiofiles import open as aopen
from aiofiles import os as aos
from asyncer import asyncify

from ark_operator.steam import steamcmd_run

if TYPE_CHECKING:
    from pathlib import Path
    from subprocess import CompletedProcess

    from ark_operator.data import Steam

ARK_SERVER_APP_ID = 2430930
_LOGGER = logging.getLogger(__name__)
MAP_NAME_LOOKUP = {
    "Aberration_WP": "Aberration",
    "BobsMissions_WP": "Club Ark",
    "Extinction_WP": "Extinction",
    "ScorchedEarth_WP": "Scorched Earth",
    "TheCenter_WP": "The Center",
    "TheIsland_WP": "The Island",
}

CAMEL_RE = re.compile(r"((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))")


async def install_ark(
    ark_dir: Path, *, steam_dir: Path, validate: bool = True
) -> CompletedProcess[str]:
    """Install ARK server."""

    cmd = [
        "+@ShutdownOnFailedCommand 1",
        "+@NoPromptForPassword 1",
        "+@sSteamCmdForcePlatformType windows",
        f"+force_install_dir {ark_dir}",
        "+login anonymous",
        f"+app_update {ARK_SERVER_APP_ID}",
    ]
    if validate:
        cmd.append("validate")
    cmd.append("+quit")
    return await steamcmd_run(" ".join(cmd), install_dir=steam_dir, retries=3)


async def get_ark_buildid(src: Path) -> int | None:
    """Get buildid for ARK install."""

    _LOGGER.debug("get buildid: %s", src)
    src_manifest_file = src / "steamapps" / f"appmanifest_{ARK_SERVER_APP_ID}.acf"
    if not await aos.path.exists(src_manifest_file):
        _LOGGER.debug("src manifest does not exist")
        return None

    async with aopen(src_manifest_file) as f:
        data = await f.read()
        src_manifest = vdf.loads(data)

    return int(src_manifest["AppState"]["buildid"])


@asyncify
def _get_steam_build_id(steam: Steam, app_id: int) -> int:
    return int(steam.cdn.get_app_depot_info(app_id)["branches"]["public"]["buildid"])


async def has_newer_version(steam: Steam, src: Path) -> bool:
    """Check if src ARK install has a newer version."""

    _LOGGER.debug("check update: %s", src)
    src_buildid = await get_ark_buildid(src)
    if not src_buildid:
        return True

    latest_buildid = await _get_steam_build_id(steam, ARK_SERVER_APP_ID)

    _LOGGER.debug("latest: %s, src: %s", latest_buildid, src_buildid)
    return latest_buildid > src_buildid


async def is_ark_newer(src: Path, dest: Path) -> bool:
    """Check if src ARK install is newer then dest."""

    _LOGGER.debug("src: %s, dest: %s", src, dest)
    src_buildid = await get_ark_buildid(src)
    if not src_buildid:
        return False

    dest_buildid = await get_ark_buildid(dest)
    if not dest_buildid:
        return True

    _LOGGER.debug("src buildid: %s, dest buildid: %s", src_buildid, dest_buildid)
    return src_buildid > dest_buildid


async def copy_ark(src: Path, dest: Path) -> None:
    """Copy ARK install to another."""

    _LOGGER.info("Checking if can copy src ARK (%s) to dest ARK (%s)", src, dest)

    if src == dest:
        _LOGGER.info("src ARK is same as dest ARK")
        return

    if not await is_ark_newer(src, dest):
        _LOGGER.info("src ARK is not newer")
        return

    if dest.exists():
        _LOGGER.info("Removing dest ARK")
        await aioshutil.rmtree(dest)  # type: ignore[call-arg]

    _LOGGER.info("Copying src ARK to dest ARK")
    await aioshutil.copytree(src, dest)


@lru_cache(maxsize=20)
def get_map_name(map_id: str) -> str:
    """Get map name from map ID."""

    if map_name := MAP_NAME_LOOKUP.get(map_id):
        return map_name

    map_name = map_id.lstrip("M_")
    if map_name.endswith("_SOTF"):
        map_name = map_name.rstrip("_SOTF")
        map_name = CAMEL_RE.sub(r" \1", map_name)
        map_name = f"The Survival of the Fittest ({map_name})"
    else:
        map_name = map_name.rstrip("WP").rstrip("_")
        map_name = CAMEL_RE.sub(r" \1", map_name)

    return map_name.replace("_", "").title()
