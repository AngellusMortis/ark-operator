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
from environs import Env

if TYPE_CHECKING:
    from pathlib import Path

    from ark_operator.steam import Steam

_LOGGER = logging.getLogger(__name__)
ENV = Env()

ARK_SERVER_APP_ID = 2430930
ARK_SERVER_IMAGE_VERSION = ENV("ARK_SERVER_IMAGE_VERSION", "v0.7.0")
MAP_NAME_LOOKUP = {
    "Aberration_WP": "Aberration",
    "BobsMissions_WP": "Club Ark",
    "Extinction_WP": "Extinction",
    "ScorchedEarth_WP": "Scorched Earth",
    "TheCenter_WP": "The Center",
    "TheIsland_WP": "The Island",
}
ALL_CANONICAL = ["TheIsland_WP", "ScorchedEarth_WP", "Aberration_WP", "Extinction_WP"]
ALL_OFFICIAL = [
    "TheIsland_WP",
    "TheCenter_WP",
    "ScorchedEarth_WP",
    "Aberration_WP",
    "Extinction_WP",
]
MAP_SHORTHAND_LOOKUP = {
    "@canonical": ["BobsMissions_WP", *ALL_CANONICAL],
    "@canonicalNoClub": ALL_CANONICAL,
    "@official": ["BobsMissions_WP", *ALL_OFFICIAL],
    "@officialNoClub": ALL_OFFICIAL,
}


ERROR_NO_ALL = "@all can only be used if a list of all maps is passed in."

CAMEL_RE = re.compile(r"((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))")


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
def _get_latest_buildid(steam: Steam, app_id: int) -> int:
    return int(steam.cdn.get_app_depot_info(app_id)["branches"]["public"]["buildid"])


async def get_latest_ark_buildid(steam: Steam) -> int:
    """Get latest version of ARK."""

    return await _get_latest_buildid(steam, ARK_SERVER_APP_ID)


async def has_newer_version(steam: Steam, src: Path) -> bool:
    """Check if src ARK install has a newer version."""

    _LOGGER.debug("check update: %s", src)
    src_buildid = await get_ark_buildid(src)
    if not src_buildid:
        return True

    latest_buildid = await get_latest_ark_buildid(steam)

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


async def copy_ark(src: Path, dest: Path, *, dry_run: bool = False) -> None:
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
        if not dry_run:
            await aioshutil.rmtree(dest)

    _LOGGER.info("Copying src ARK to dest ARK")
    if not dry_run:
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


@lru_cache(maxsize=20)
def get_map_slug(map_id: str, max_length: int = 11) -> str:
    """Get map name from map ID."""

    map_name = get_map_name(map_id)
    map_name = (
        map_name.lower().replace("survival of the fittest", "sotf").replace("heim", "")
    )
    no_the = map_name.replace("the ", "").replace("(", "").replace(")", "").strip()
    slug = no_the.replace(" ", "-")
    if len(slug) > max_length:
        slug = "".join([s[0] for s in no_the.split(" ")])

    return slug


def order_maps(maps: list[str]) -> list[str]:
    """Order maps in a consistent way."""

    ordered_maps = []
    map_order = MAP_SHORTHAND_LOOKUP["@official"]
    for map_id in map_order:
        if map_id in maps:
            ordered_maps.append(map_id)
            maps.remove(map_id)
    ordered_maps += sorted(maps)

    return ordered_maps


def expand_maps(maps: list[str], *, all_maps: list[str] | None = None) -> list[str]:
    """Expand map shorthands into list of maps."""

    _expanded = set()
    remove_maps = set()
    for map_id in maps:
        if map_id == "@all":
            if all_maps is None:
                raise ValueError(ERROR_NO_ALL)
            _expanded |= set(all_maps)
        elif map_id.startswith("-"):
            remove_maps.add(map_id[1:])
        elif expanded_maps := MAP_SHORTHAND_LOOKUP.get(map_id):
            _expanded |= set(expanded_maps)
        else:
            _expanded.add(map_id)

    _expanded -= remove_maps
    return order_maps(list(_expanded))
