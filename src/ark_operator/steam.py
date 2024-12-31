"""Steam utils."""

import logging
import platform
import tarfile
import zipfile
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess

import aioshutil
import httpx
from aiofiles import open as aopen
from aiofiles import os as aos
from aiofiles.tempfile import TemporaryDirectory
from asyncer import asyncify

from ark_operator.command import run_async
from ark_operator.exceptions import SteamCMDError

ERROR_UNSUPPORTED = (
    "Non supported operating system. Expected Windows or Linux, got {platform}"
)
ERROR_STEAMCMD = "Error executing steamcmd"

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
        f.extractall(extract_path)  # noqa: S202


async def _extract_archive(install_dir: Path, platform: str, data: bytes) -> None:
    async with TemporaryDirectory() as tmp:
        path = Path(tmp) / "steamcmd_archive"
        async with aopen(path, "wb") as f:
            await f.write(data)

        if platform == "Windows":
            await _extract_zip(path, install_dir)
            return

        await _extract_tar(path, install_dir)


async def install_steamcmd(install_dir: Path, *, force: bool = False) -> Path:
    """Install steamcmd."""

    if (plat := platform.system()) not in ["Windows", "Linux"]:
        raise SteamCMDError(ERROR_UNSUPPORTED.format(platform=plat))

    package = PACKAGE_LINKS[plat]
    url = package["url"]
    exe_ext = package["extension"]
    exe_path = install_dir / f"steamcmd{exe_ext}"

    if not force and await aos.path.exists(exe_path):
        _LOGGER.debug("steamcmd already installed, skipping install")
        return exe_path

    if await aos.path.exists(exe_path):
        _LOGGER.debug("Redowloading steamcmd")
        await aioshutil.rmtree(install_dir)  # type: ignore[call-arg]

    await aos.makedirs(install_dir, exist_ok=True)
    async with httpx.AsyncClient() as client:
        _LOGGER.debug("Downloading steamcmd from %s", url)
        response = await client.get(url)
        response.raise_for_status()
        data = await response.aread()
        _LOGGER.debug("Extracting steamd %s", install_dir)
        await _extract_archive(install_dir, plat, data)

    return exe_path


async def steamcmd_run(  # type: ignore[return]
    cmd: str, *, install_dir: Path, force_download: bool = False, retries: int = 0
) -> CompletedProcess[str]:
    """Run steamcmd."""

    steamcmd = await install_steamcmd(install_dir, force=force_download)
    while retries >= 0:  # noqa: RET503
        try:
            return await run_async(
                f"{steamcmd} {cmd}", check=True, output_level=logging.INFO
            )
        except CalledProcessError as ex:
            if retries > 0:
                retries -= 1
                _LOGGER.warning(ERROR_STEAMCMD, exc_info=ex)
            else:
                raise SteamCMDError(ERROR_STEAMCMD) from ex
