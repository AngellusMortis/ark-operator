"""ARK helper functions."""

from __future__ import annotations

import logging
import re
import shutil
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import vdf
from asyncer import asyncify
from pysteamcmdwrapper import SteamCMD_command

if TYPE_CHECKING:
    from pathlib import Path

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


def install_ark_sync(steam: Steam, *, ark_dir: Path, validate: bool = True) -> None:
    """Install ARK server."""

    cmd = SteamCMD_command()
    cmd.custom("+@sSteamCmdForcePlatformType windows")
    cmd.force_install_dir(ark_dir)
    cmd.app_update(ARK_SERVER_APP_ID, validate=validate)
    steam.execute(cmd, n_tries=3)


install_ark = asyncify(install_ark_sync)


def get_ark_buildid_sync(src: Path) -> int | None:
    """Get buildid for ARK install."""

    _LOGGER.debug("get buildid: %s", src)
    src_manifest_file = src / "steamapps" / f"appmanifest_{ARK_SERVER_APP_ID}.acf"
    if not src_manifest_file.exists():
        _LOGGER.debug("src manifest does not exist")
        return None

    with src_manifest_file.open() as f:
        src_manifest = vdf.load(f)

    return int(src_manifest["AppState"]["buildid"])


get_ark_buildid = asyncify(get_ark_buildid_sync)


def has_newer_version_sync(steam: Steam, src: Path) -> bool:
    """Check if src ARK install has a newer version."""

    _LOGGER.debug("check update: %s", src)
    src_buildid = get_ark_buildid_sync(src)
    if not src_buildid:
        return True

    latest_buildid = int(
        steam.cdn.get_app_depot_info(ARK_SERVER_APP_ID)["branches"]["public"]["buildid"]
    )

    _LOGGER.debug("latest: %s, src: %s", latest_buildid, src_buildid)
    return latest_buildid > src_buildid


has_newer_version = asyncify(has_newer_version_sync)


def is_ark_newer_sync(src: Path, dest: Path) -> bool:
    """Check if src ARK install is newer then dest."""

    _LOGGER.debug("src: %s, dest: %s", src, dest)
    src_buildid = get_ark_buildid_sync(src)
    if not src_buildid:
        return False

    dest_buildid = get_ark_buildid_sync(dest)
    if not dest_buildid:
        return True

    _LOGGER.debug("src buildid: %s, dest buildid: %s", src_buildid, dest_buildid)
    return src_buildid > dest_buildid


is_ark_newer = asyncify(is_ark_newer_sync)


def copy_ark_sync(src: Path, dest: Path) -> None:
    """Copy ARK install to another."""

    _LOGGER.info("Checking if can copy src ARK (%s) to dest ARK (%s)", src, dest)

    if not is_ark_newer_sync(src, dest):
        _LOGGER.info("src ARK is not newer")
        return

    if dest.exists():
        _LOGGER.info("Removing dest ARK")
        shutil.rmtree(dest)

    _LOGGER.info("Copying src ARK to dest ARK")
    shutil.copytree(src, dest)


copy_ark = asyncify(copy_ark_sync)


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