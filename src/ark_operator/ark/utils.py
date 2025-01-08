"""ARK helper functions."""

from __future__ import annotations

import asyncio
import logging
import re
from configparser import ConfigParser
from dataclasses import dataclass
from functools import lru_cache
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Literal, overload

import aioshutil
import vdf
from aiofiles import open as aopen
from aiofiles import os as aos
from asyncer import asyncify

from ark_operator.command import run_async

if TYPE_CHECKING:
    from pathlib import Path
    from subprocess import CompletedProcess

    from ark_operator.steam import Steam

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
ARK_RUN_TEMPLATE = '{proton_path!s} run {server_path!s} {map_name}?SessionName="{session_name}"?RCONEnabled=True?RCONPort={rcon_port}?ServerAdminPassword={rcon_password} -port={game_port} -WinLiveMaxPlayers={max_players} -clusterid={cluster_id} -ClusterDirOverride={data_dir!s} -NoTransferFromFiltering {extra_args}'  # noqa: E501

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
    ordered_maps = []
    map_order = MAP_SHORTHAND_LOOKUP["@official"]
    for map_id in map_order:
        if map_id in _expanded:
            ordered_maps.append(map_id)
            _expanded.remove(map_id)
    ordered_maps += list(_expanded)

    return ordered_maps


async def _make_sure_file_exists(
    path: Path, *, force_delete: bool = True, dry_run: bool = False
) -> None:
    await aos.makedirs(path.parent, exist_ok=True)
    exists = await aos.path.exists(path)
    if not dry_run and exists and force_delete:
        await aos.remove(path)
        exists = False

    if not dry_run and not await aos.path.exists(path):
        path.touch()


async def _ensure_symlink(target: Path, link: Path, *, is_dir: bool = True) -> None:
    if await aos.path.exists(link):
        if await aos.path.islink(link):
            if await aos.readlink(str(link)) == str(target):
                _LOGGER.debug("Symlink exists %s -> %s", link, target)
                return
            _LOGGER.debug("Symlink %s exists, but mismatched", link)
            await aos.remove(link)
        else:
            _LOGGER.debug("Directory %s instead of symlink, deleteing", link)
            await aioshutil.rmtree(link)

    _LOGGER.info("Creating symlink %s -> %s", link, target)
    await aos.symlink(target, link, target_is_directory=is_dir)


@dataclass
class ArkServer:
    """ARK server run wrapper."""

    server_dir: Path
    data_dir: Path
    map_name: str
    session_name: str
    rcon_port: int
    rcon_password: str
    game_port: int
    max_players: int
    cluster_id: str
    battleye: bool
    allowed_platforms: list[Literal["ALL", "PS5", "XSX", "PC", "WINGDK"]]
    whitelist: bool
    multihome_ip: str | None

    @property
    def list_dir(self) -> Path:
        """Directory with whitelist/bypass list."""

        return self.data_dir / "lists"

    @property
    def ark_dir(self) -> Path:
        """ARK install dir."""

        return self.server_dir / "ark"

    @property
    def binary_dir(self) -> Path:
        """ARK binary dir."""

        return self.ark_dir / "ShooterGame" / "Binaries" / "Win64"

    @property
    def mod_dir(self) -> Path:
        """ARK save dir."""

        return self.data_dir / "maps" / self.map_name / "mods"

    @property
    def saved_dir(self) -> Path:
        """ARK save dir."""

        return self.data_dir / "maps" / self.map_name / "saved"

    @property
    def compatdata_dir(self) -> Path:
        """ARK compatdata dir."""

        return self.data_dir / "maps" / self.map_name / "compatdata"

    @property
    def config_dir(self) -> Path:
        """ARK Config dir."""

        return self.saved_dir / "Config" / "WindowsServer"

    @property
    def steam_dir(self) -> Path:
        """Steam install dir."""

        return self.server_dir / "steam"

    @property
    def proton_dir(self) -> Path:
        """Proton install dir."""

        from ark_operator.steam import PROTON_VERSION

        return (
            self.steam_dir
            / ".steam"
            / "root"
            / "compatibilitytools.d"
            / f"GE-Proton{PROTON_VERSION}"
        )

    @property
    def log_file(self) -> Path:
        """ARK log file path."""

        return self.saved_dir / "Logs" / "ShooterGame.log"

    @property
    def whitelist_file(self) -> Path:
        """Whitelist file for server."""

        return self.list_dir / "PlayersExclusiveJoinList.txt"

    @property
    def bypass_file(self) -> Path:
        """Bypass list file for server."""

        return self.list_dir / "PlayersJoinNoCheckList.txt"

    @property
    def server_platforms(self) -> list[Literal["ALL", "PS5", "XSX", "PC", "WINGDK"]]:
        """Allowed server platforms."""

        if "ALL" in self.allowed_platforms:
            return ["ALL"]

        return self.allowed_platforms

    @property
    def run_command(self) -> str:
        """ARK server run command."""

        extra_args = ["ServerPlatform" + "+".join(self.server_platforms)]
        if not self.battleye:
            extra_args.append("NoBattlEye")
        if self.whitelist:
            extra_args.append("exclusivejoin")
        if self.multihome_ip:
            extra_args.append("MULTIHOME")
        if self.map_name == "BobsMissions_WP":
            extra_args.append("mods=1005639")

        args = f"-{' -'.join(extra_args)}"
        return ARK_RUN_TEMPLATE.format(
            proton_path=self.proton_dir / "proton",
            server_path=self.binary_dir / "ArkAscendedServer.exe",
            map_name=self.map_name,
            session_name=self.session_name,
            rcon_port=self.rcon_port,
            rcon_password=self.rcon_password,
            game_port=self.game_port,
            max_players=self.max_players,
            cluster_id=self.cluster_id,
            data_dir=self.data_dir,
            extra_args=args,
        )

    def make_game_user_settings(self) -> ConfigParser:
        """GameUserSettings.ini file."""

        conf = ConfigParser()
        conf["ServerSettings"] = {
            "RCONEnabled": "True",
            "RCONPort": str(self.rcon_port),
            "ServerAdminPassword": self.rcon_password,
        }
        conf["SessionSettings"] = {
            "Port": str(self.game_port),
            "SessionName": self.session_name,
        }

        if self.multihome_ip:
            conf["MultiHome"] = {"Multihome": "True"}
            conf["SessionSettings"]["MultiHome"] = self.multihome_ip

        return conf

    async def _write_config(self) -> None:
        conf = self.make_game_user_settings()
        with StringIO() as ss:
            conf.write(ss)
            ss.seek(0)
            async with aopen(self.config_dir / "GameUserSettings.ini", "w") as f:
                await f.write(ss.read().strip())

    @overload
    async def run(
        self, *, dry_run: Literal[False] = False
    ) -> CompletedProcess[str]: ...  # pragma: no cover

    @overload
    async def run(
        self, *, dry_run: Literal[True]
    ) -> CompletedProcess[None]: ...  # pragma: no cover

    @overload
    async def run(
        self, *, dry_run: bool
    ) -> CompletedProcess[str] | CompletedProcess[None]: ...  # pragma: no cover

    async def run(
        self, *, dry_run: bool = False
    ) -> CompletedProcess[str] | CompletedProcess[None]:
        """Run ARK server."""

        await _make_sure_file_exists(self.whitelist_file)
        await _make_sure_file_exists(self.bypass_file)
        await _ensure_symlink(self.saved_dir, self.ark_dir / "ShooterGame" / "Saved")
        await _ensure_symlink(self.mod_dir, self.binary_dir / "ShooterGame")
        await _ensure_symlink(
            self.whitelist_file,
            self.binary_dir / "PlayersExclusiveJoinList.txt",
            is_dir=False,
        )
        await _ensure_symlink(
            self.whitelist_file,
            self.binary_dir / "PlayersJoinNoCheckList.txt",
            is_dir=False,
        )
        await _make_sure_file_exists(self.log_file)
        await self._write_config()

        task = asyncio.create_task(
            run_async(
                self.run_command,
                dry_run=dry_run,
                env={
                    "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(self.compatdata_dir),
                    "STEAM_COMPAT_DATA_PATH": str(self.compatdata_dir),
                },
            )
        )
        async with aopen(self.log_file) as f:
            while True:
                if line := await f.readline():
                    _LOGGER.info(line.strip())
                    continue

                await asyncio.sleep(0.1)
                if task.done():
                    break

        return await task
