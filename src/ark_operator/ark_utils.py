"""ARK helper functions."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import vdf
from pysteamcmdwrapper import SteamCMD_command

if TYPE_CHECKING:
    from pathlib import Path

    from ark_operator.data import Steam

ARK_SERVER_APP_ID = 2430930
_LOGGER = logging.getLogger(__name__)


def install_ark(steam: Steam, *, ark_dir: Path) -> None:
    """Install ARK server."""

    cmd = SteamCMD_command()
    cmd.custom("+@sSteamCmdForcePlatformType windows")
    cmd.force_install_dir(ark_dir)
    cmd.app_update(ARK_SERVER_APP_ID, validate=False)
    steam.cmd.execute(cmd, n_tries=3)


def get_ark_buildid(src: Path) -> int | None:
    """Get buildid for ARK install."""

    _LOGGER.debug("get buildid: %s", src)
    src_manifest_file = src / "steamapps" / f"appmanifest_{ARK_SERVER_APP_ID}.acf"
    if not src_manifest_file.exists():
        _LOGGER.debug("src manifest does not exist")
        return None

    with src_manifest_file.open() as f:
        src_manifest = vdf.load(f)

    return int(src_manifest["AppState"]["buildid"])


def has_newer_version(steam: Steam, src: Path) -> bool:
    """Check if src ARK install has a newer version."""

    _LOGGER.debug("check update: %s", src)
    src_buildid = get_ark_buildid(src)
    if not src_buildid:
        return True

    latest_buildid = int(
        steam.cdn.get_app_depot_info(ARK_SERVER_APP_ID)["branches"]["public"]["buildid"]
    )

    _LOGGER.debug("latest: %s, src: %s", latest_buildid, src_buildid)
    return latest_buildid > src_buildid


def is_ark_newer(src: Path, dest: Path) -> bool:
    """Check if src ARK install is newer then dest."""

    _LOGGER.debug("src: %s, dest: %s", src, dest)
    src_buildid = get_ark_buildid(src)
    if not src_buildid:
        return False

    dest_buildid = get_ark_buildid(dest)
    if not dest_buildid:
        return True

    _LOGGER.debug("src buildid: %s, dest buildid: %s", src_buildid, dest_buildid)
    return src_buildid > dest_buildid


def copy_ark(src: Path, dest: Path) -> None:
    """Copy ARK install to another."""

    _LOGGER.info("Checking if can copy src ARK (%s) to dest ARK (%s)", src, dest)

    if not is_ark_newer(src, dest):
        _LOGGER.info("src ARK is not newer")
        return

    if dest.exists():
        _LOGGER.info("Removing dest ARK")
        shutil.rmtree(dest)

    _LOGGER.info("Copying src ARK to dest ARK")
    shutil.copytree(src, dest)