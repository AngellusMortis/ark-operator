"""ARK helper functions."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, overload

from aiofiles import open as aopen
from aiofiles import os as aos

from ark_operator.ark.conf import (
    IniConf,
    merge_conf,
    read_config,
    read_config_from_lines,
    write_config,
)
from ark_operator.command import run_async
from ark_operator.utils import ensure_symlink, touch_file

if TYPE_CHECKING:
    from pathlib import Path
    from subprocess import CompletedProcess


_LOGGER = logging.getLogger(__name__)
ARK_RUN_TEMPLATE = '{proton_path!s} run {server_path!s} {map_name}?SessionName="{session_name}"?RCONEnabled=True?RCONPort={rcon_port}{extra_params}?ServerAdminPassword={rcon_password} -port={game_port} -WinLiveMaxPlayers={max_players} -clusterid={cluster_id} -ClusterDirOverride={data_dir!s} -NoTransferFromFiltering {extra_options}'  # noqa: E501
MANAGED_PARAMS = {"SessionName", "RCONEnabled", "RCONPort", "ServerAdminPassword"}
MANAGED_OPTIONS = {
    "port",
    "WinLiveMaxPlayers",
    "clusterid",
    "ClusterDirOverride",
    "NoTransferFromFiltering",
    "ServerPlatform",
    "NoBattlEye",
    "exclusivejoin",
    "MULTIHOME",
    "mods",
}

ERROR_MANAGED = "{items} are managed {type_}, they cannot be proved manually."


async def _make_sure_file_exists(
    path: Path, *, force_delete: bool = True, dry_run: bool = False
) -> None:
    await aos.makedirs(path.parent, exist_ok=True)
    exists = await aos.path.exists(path)
    if not dry_run and exists and force_delete:
        await aos.remove(path)
        exists = False

    if not dry_run and not await aos.path.exists(path):
        await touch_file(path)


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
    parameters: list[str]
    options: list[str]
    mods: list[str]
    global_config: Path | None = None
    map_config: Path | None = None
    global_ark_config: Path | None = None
    map_ark_config: Path | None = None
    global_config_secrets: str | None = None

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
    def marker_file(self) -> Path:
        """File to track if server has started."""

        return self.saved_dir / ".started"

    @property
    def server_platforms(self) -> list[Literal["ALL", "PS5", "XSX", "PC", "WINGDK"]]:
        """Allowed server platforms."""

        if "ALL" in self.allowed_platforms:
            return ["ALL"]

        return sorted(self.allowed_platforms.copy())

    def make_params(self) -> list[str]:
        """List of ARK server params (?)."""

        extra_params = []
        if self.parameters:
            overlap = {o.split("=")[0] for o in self.parameters}.intersection(
                MANAGED_PARAMS
            )
            if overlap:
                raise ValueError(
                    ERROR_MANAGED.format(items=overlap, type_="parameters")
                )
            extra_params = self.parameters.copy()

        return extra_params

    def make_opts(self) -> list[str]:
        """List of ARK server options (-)."""

        mods = self.mods.copy()
        extra_options = ["ServerPlatform=" + "+".join(self.server_platforms)]
        if not self.battleye:
            extra_options.append("NoBattlEye")
        if self.whitelist:
            extra_options.append("exclusivejoin")
        if self.multihome_ip:
            extra_options.append("MULTIHOME")
        if self.map_name == "BobsMissions_WP":
            mods.insert(0, "1005639")
        if self.options:
            overlap = {o.split("=")[0] for o in self.options}.intersection(
                MANAGED_OPTIONS
            )
            if overlap:
                raise ValueError(ERROR_MANAGED.format(items=overlap, type_="options"))
            extra_options += self.options

        if mods:
            extra_options.append(f"mods={','.join(mods)}")

        return extra_options

    def make_run_command(self) -> str:
        """ARK server run command."""

        options = f"-{' -'.join(self.make_opts())}"
        params = "?".join(self.make_params())
        if params:
            params = f"?{params}"
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
            extra_options=options,
            extra_params=params,
        )

    async def _read_gus(self, path: Path) -> IniConf | None:
        if not await aos.path.exists(path):
            _LOGGER.debug("%s (%s) does not exist", path.name, path)
            return None

        _LOGGER.debug("Reading %s (%s)", path.name, path)
        return await read_config(path)

    def _make_managed_gus(self) -> IniConf:
        conf: IniConf = {
            "ServerSettings": {
                "RCONEnabled": "True",
                "RCONPort": str(self.rcon_port),
                "ServerAdminPassword": self.rcon_password,
            },
            "SessionSettings": {
                "Port": str(self.game_port),
                "SessionName": self.session_name,
            },
        }

        if self.multihome_ip:
            conf["MultiHome"] = {"Multihome": "True"}
            conf["SessionSettings"]["MultiHome"] = self.multihome_ip

        if self.global_config_secrets:
            _LOGGER.debug("Merging secrets info GameUserSettings.ini")
            conf = merge_conf(
                conf, read_config_from_lines(self.global_config_secrets.split("\n"))
            )

        return conf

    async def make_game_user_settings(self) -> IniConf:
        """GameUserSettings.ini file."""

        conf: IniConf | None = None
        if self.global_config:
            _LOGGER.debug("Reading global GameUserSettings.ini")
            conf = await self._read_gus(self.global_config)

        if self.map_config:
            _LOGGER.debug("Reading map GameUserSettings.ini")
            conf = merge_conf(conf, await self._read_gus(self.map_config))

        _log = _LOGGER.info
        if conf is None:
            _log = _LOGGER.debug
        _log("Merging managed GameUserSettings.ini onto user provided one")
        return merge_conf(conf, self._make_managed_gus(), warn=True)

    async def make_game(self) -> IniConf | None:
        """Game.ini file."""

        conf: IniConf | None = None
        if self.global_ark_config:
            _LOGGER.debug("Reading global Game.ini")
            conf = await self._read_gus(self.global_ark_config)

        if self.map_ark_config:
            _LOGGER.debug("Reading map Game.ini")
            conf = merge_conf(conf, await self._read_gus(self.map_ark_config))

        return conf

    @overload
    async def run(
        self, *, read_only: bool = False, dry_run: Literal[False] = False
    ) -> CompletedProcess[str]: ...  # pragma: no cover

    @overload
    async def run(
        self, *, read_only: bool = False, dry_run: Literal[True]
    ) -> CompletedProcess[None]: ...  # pragma: no cover

    @overload
    async def run(
        self, *, read_only: bool = False, dry_run: bool
    ) -> CompletedProcess[str] | CompletedProcess[None]: ...  # pragma: no cover

    async def run(
        self,
        *,
        read_only: bool = False,
        dry_run: bool = False,
    ) -> CompletedProcess[str] | CompletedProcess[None]:
        """Run ARK server."""

        if not read_only:  # pragma: no branch
            await _make_sure_file_exists(self.whitelist_file, force_delete=False)
            await _make_sure_file_exists(self.bypass_file, force_delete=False)
            await ensure_symlink(self.saved_dir, self.ark_dir / "ShooterGame" / "Saved")
            await ensure_symlink(self.mod_dir, self.binary_dir / "ShooterGame")

        await aos.makedirs(self.compatdata_dir, exist_ok=True)
        if await aos.path.exists(self.marker_file):
            await aos.remove(self.marker_file)
        await _make_sure_file_exists(self.log_file)
        _LOGGER.debug("Writing configs")
        conf = await self.make_game_user_settings()
        await aos.makedirs(self.config_dir, exist_ok=True)
        await write_config(conf, self.config_dir / "GameUserSettings.ini")
        game_conf = await self.make_game()
        if game_conf:
            await write_config(game_conf, self.config_dir / "Game.ini")

        _LOGGER.debug("Starting server")
        task = asyncio.create_task(
            run_async(
                self.make_run_command(),
                dry_run=dry_run,
                env={
                    "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(self.compatdata_dir),
                    "STEAM_COMPAT_DATA_PATH": str(self.compatdata_dir),
                },
                echo=True,
            )
        )
        await asyncio.sleep(0.01)
        async with aopen(self.log_file) as f:
            while True:
                with suppress(TimeoutError):
                    async with asyncio.timeout(5):
                        line = await f.readline()

                if line:
                    _LOGGER.info(line.strip())
                    if "has successfully started" in line:  # pragma: no branch
                        _LOGGER.debug(
                            "Creating startup marker file %s", self.marker_file
                        )
                        await touch_file(self.marker_file)
                    continue

                await asyncio.sleep(0.1)
                if task.done():  # pragma: no branch
                    break

        return await task
