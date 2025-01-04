"""Steam utils."""

from __future__ import annotations

import logging
import platform
import tarfile
import warnings
import zipfile
from dataclasses import dataclass
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from typing import Literal, overload

import aioshutil
import httpx
from aiofiles import open as aopen
from aiofiles import os as aos
from aiofiles.tempfile import TemporaryDirectory
from asyncer import asyncify

from ark_operator.ark import ARK_SERVER_APP_ID, copy_ark, has_newer_version
from ark_operator.command import run_async
from ark_operator.decorators import sync_only
from ark_operator.exceptions import SteamCMDError

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=r"invalid escape sequence '\\-'")
    warnings.filterwarnings("ignore", message=r"invalid escape sequence '\\\('")
    warnings.filterwarnings("ignore", message=r"invalid escape sequence '\\d'")
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    from steam.client import SteamClient
    from steam.client.cdn import CDNClient

ERROR_UNSUPPORTED = (
    "Non supported operating system. Expected Windows or Linux, got {platform}"
)
ERROR_STEAMCMD = "Error executing steamcmd"
ERROR_FAILED_INSTALL = "Failed to install steamcmd"
ERROR_DOWNLOAD_FAILED = "Failed to download steamcmd"

PACKAGE_LINKS = {
    "Windows": {
        "url": "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip",
        "extension": ".exe",
        "d_extension": ".zip",
    },
    "Linux": {
        "url": "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz",
        "extension": ".sh",
        "d_extension": ".tar.gz",
    },
}

_LOGGER = logging.getLogger(__name__)


@asyncify
def _extract_zip(path: Path, extract_path: Path) -> None:
    with zipfile.ZipFile(path, "r") as f:
        f.extractall(extract_path)  # noqa: S202


@asyncify
def _extract_tar(path: Path, extract_path: Path) -> None:
    with tarfile.open(path, "r:gz") as f:
        f.extractall(extract_path, filter="data")


async def _extract_archive(install_dir: Path, platform: str, data: bytes) -> None:
    async with TemporaryDirectory() as tmp:
        path = Path(tmp) / "steamcmd_archive"
        async with aopen(path, "wb") as f:
            await f.write(data)

        if platform == "Windows":
            await _extract_zip(path, install_dir)
            return

        await _extract_tar(path, install_dir)


async def install_steamcmd(
    install_dir: Path, *, force: bool = False, dry_run: bool = False
) -> Path:
    """Install steamcmd."""

    if (plat := platform.system()) not in ["Windows", "Linux"]:
        raise SteamCMDError(ERROR_UNSUPPORTED.format(platform=plat))

    package = PACKAGE_LINKS[plat]
    url = package["url"]
    exe_ext = package["extension"]
    exe_path = install_dir / f"steamcmd{exe_ext}"

    exists = await aos.path.exists(exe_path)
    if not force and exists:
        _LOGGER.debug("steamcmd already installed, skipping install")
        return exe_path

    if exists:
        _LOGGER.debug("Redowloading steamcmd")
        if not dry_run:
            await aioshutil.rmtree(install_dir)

    if not dry_run:
        await aos.makedirs(install_dir, exist_ok=True)
    async with httpx.AsyncClient() as client:
        _LOGGER.debug("Downloading steamcmd from %s", url)
        if not dry_run:
            try:
                response = await client.get(url)
                response.raise_for_status()
                data = await response.aread()
            except Exception as ex:
                raise SteamCMDError(ERROR_DOWNLOAD_FAILED) from ex

        _LOGGER.debug("Extracting steamcmd %s", install_dir)
        if not dry_run:
            await _extract_archive(install_dir, plat, data)

    if not dry_run and not await aos.path.exists(exe_path):
        raise SteamCMDError(ERROR_FAILED_INSTALL)

    return exe_path


@overload
async def steamcmd_run(
    cmd: str,
    *,
    install_dir: Path,
    force_download: bool = False,
    retries: int = 0,
    dry_run: Literal[False] = False,
) -> CompletedProcess[str]: ...  # pragma: no cover


@overload
async def steamcmd_run(
    cmd: str,
    *,
    install_dir: Path,
    force_download: bool = False,
    retries: int = 0,
    dry_run: Literal[True],
) -> CompletedProcess[None]: ...  # pragma: no cover


@overload
async def steamcmd_run(
    cmd: str,
    *,
    install_dir: Path,
    force_download: bool = False,
    retries: int = 0,
    dry_run: bool,
) -> CompletedProcess[str] | CompletedProcess[None]: ...  # pragma: no cover


async def steamcmd_run(  # type: ignore[return]
    cmd: str,
    *,
    install_dir: Path,
    force_download: bool = False,
    retries: int = 0,
    dry_run: bool = False,
) -> CompletedProcess[str] | CompletedProcess[None]:
    """Run steamcmd."""

    steamcmd = await install_steamcmd(
        install_dir, force=force_download, dry_run=dry_run
    )
    while retries >= 0:  # noqa: RET503  # pragma: no branch
        try:
            return await run_async(
                f"{steamcmd} {cmd}",
                check=True,
                output_level=logging.INFO,
                dry_run=dry_run,
            )
        except CalledProcessError as ex:
            if retries > 0:
                retries -= 1
                _LOGGER.warning(ERROR_STEAMCMD, exc_info=ex)
            else:
                raise SteamCMDError(ERROR_STEAMCMD) from ex


@dataclass
class Steam:
    """Steam wrapper."""

    install_dir: Path

    _api: SteamClient | None = None
    _cdn: CDNClient | None = None

    @property
    @sync_only()
    def api(self) -> SteamClient:
        """Get SteamClient."""

        if self._api is None:  # pragma: no branch
            self._api = SteamClient()
            self._api.anonymous_login()

        return self._api

    @property
    @sync_only()
    def cdn(self) -> CDNClient:
        """Get CDNClient."""

        if self._cdn is None:  # pragma: no branch
            self._cdn = CDNClient(self.api)

        return self._cdn

    @overload
    async def cmd(
        self,
        cmd: str,
        *,
        force_download: bool = False,
        retries: int = 3,
        dry_run: Literal[False] = False,
    ) -> CompletedProcess[str]: ...  # pragma: no cover

    @overload
    async def cmd(
        self,
        cmd: str,
        *,
        force_download: bool = False,
        retries: int = 3,
        dry_run: Literal[True],
    ) -> CompletedProcess[None]: ...  # pragma: no cover

    @overload
    async def cmd(
        self,
        cmd: str,
        *,
        force_download: bool = False,
        retries: int = 3,
        dry_run: bool,
    ) -> CompletedProcess[str] | CompletedProcess[None]: ...  # pragma: no cover

    async def cmd(
        self,
        cmd: str,
        *,
        force_download: bool = False,
        retries: int = 3,
        dry_run: bool = False,
    ) -> CompletedProcess[str] | CompletedProcess[None]:
        """Run steamcmd."""

        return await steamcmd_run(
            cmd,
            install_dir=self.install_dir,
            retries=retries,
            force_download=force_download,
            dry_run=dry_run,
        )

    @overload
    async def install_ark(
        self,
        ark_dir: Path,
        *,
        validate: bool = True,
        dry_run: Literal[False] = False,
    ) -> CompletedProcess[str]: ...  # pragma: no cover

    @overload
    async def install_ark(
        self,
        ark_dir: Path,
        *,
        validate: bool = True,
        dry_run: Literal[True],
    ) -> CompletedProcess[None]: ...  # pragma: no cover

    @overload
    async def install_ark(
        self,
        ark_dir: Path,
        *,
        validate: bool = True,
        dry_run: bool,
    ) -> CompletedProcess[str] | CompletedProcess[None]: ...  # pragma: no cover

    async def install_ark(
        self, ark_dir: Path, *, validate: bool = True, dry_run: bool = False
    ) -> CompletedProcess[str] | CompletedProcess[None]:
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
        return await steamcmd_run(
            " ".join(cmd),
            install_dir=self.install_dir,
            retries=3,
            dry_run=dry_run,
        )

    async def copy_ark(
        self, src_dir: Path, dest_dir: Path, *, dry_run: bool = False
    ) -> None:
        """Copy ARK server install."""

        await copy_ark(src_dir, dest_dir, dry_run=dry_run)

    async def has_newer_version(self, ark_dir: Path) -> bool:
        """Check if ARK has newer version."""

        return await has_newer_version(self, ark_dir)
