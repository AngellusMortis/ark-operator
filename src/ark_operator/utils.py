"""ARK utils."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, overload

from aiofiles import open as aopen
from aiofiles import os as aos

if TYPE_CHECKING:
    from pathlib import Path


_LOGGER = logging.getLogger(__name__)


def is_async() -> bool:
    """Test if inside asyncio thread."""

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        return loop.is_running()
    return False


async def ensure_symlink(target: Path, link: Path, *, is_dir: bool = True) -> None:
    """Ensure a symlink is setup correctly."""

    if await aos.path.exists(link):
        if await aos.path.islink(link):
            if await aos.readlink(str(link)) == str(target):
                _LOGGER.debug("Symlink exists %s -> %s", link, target)
                return
            _LOGGER.debug("Symlink %s exists, but mismatched", link)
            await aos.remove(link)
        else:
            # assume directory is volume mounted correctly
            _LOGGER.debug("Directory %s instead of symlink, skipping", link)
            return

    _LOGGER.info("Creating symlink %s -> %s", link, target)
    await aos.makedirs(link.parent, exist_ok=True)
    await aos.symlink(target, link, target_is_directory=is_dir)


async def touch_file(path: Path) -> None:
    """Bash util touch in python."""

    async with aopen(path, "a"):
        pass


@overload
def comma_list(args: list[str]) -> list[str]: ...  # pragma: no cover


@overload
def comma_list(args: None) -> None: ...  # pragma: no cover


@overload
def comma_list(args: list[str] | None) -> list[str] | None: ...  # pragma: no cover


def comma_list(args: list[str] | None) -> list[str] | None:
    """Handle list of comma seperated lists."""

    if args is None:
        return None

    if len(args) == 1 and "," in args[0]:
        args = args[0].split(",")

    return args
