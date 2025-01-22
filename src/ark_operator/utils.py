"""ARK utils."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta
from functools import lru_cache
from importlib.metadata import version
from typing import TYPE_CHECKING, overload

from aiofiles import open as aopen
from aiofiles import os as aos
from human_readable import time_delta

try:
    # python 3.11+
    from datetime import UTC
except ImportError:
    # python 3.10-
    from datetime import timezone

    UTC = timezone.utc  # noqa: UP017

if TYPE_CHECKING:
    from pathlib import Path


_LOGGER = logging.getLogger(__name__)
VERSION = version("ark_operator")

TD_PATTERN = re.compile(r"((?P<hours>\d+)h)?((?P<minutes>\d+)m)?((?P<seconds>\d+)s)?")
_INTERVALS = {
    "1h": int(timedelta(hours=1).total_seconds()),
    "30m": int(timedelta(minutes=30).total_seconds()),
    "5m": int(timedelta(minutes=5).total_seconds()),
    "1m": 60,
    "30s": 30,
    "10s": 10,
}


def utc_now() -> datetime:
    """Get current time."""

    return datetime.now(UTC)


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

    if is_dir:
        await aos.makedirs(target, exist_ok=True)
    else:
        await aos.makedirs(target.parent, exist_ok=True)
    await aos.makedirs(link.parent, exist_ok=True)

    if await aos.path.islink(link):
        if await aos.readlink(str(link)) == str(target):
            _LOGGER.debug("Symlink exists %s -> %s", link, target)
            return
        _LOGGER.debug("Symlink %s exists, but mismatched", link)
        await aos.remove(link)
    elif await aos.path.exists(link):
        if not await aos.path.isdir(link):
            _LOGGER.debug("File %s is not symlink, deleting", link)
            await aos.remove(link)
        else:
            # assume directory is volume mounted correctly
            _LOGGER.debug("Directory %s instead of symlink, skipping", link)
            return

    _LOGGER.info("Creating symlink %s -> %s", link, target)
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


def convert_timedelta(value: str | int) -> timedelta | str:
    """Convert string to timedelta."""

    if isinstance(value, int):
        return timedelta(seconds=value)

    value = str(value)
    if match := TD_PATTERN.match(value):  # pragma: no branch
        hours = match.group("hours")
        minutes = match.group("minutes")
        seconds = match.group("seconds")
        if hours or minutes or seconds:
            return timedelta(
                hours=int(hours or "0"),
                minutes=int(minutes or "0"),
                seconds=int(seconds or "0"),
            )
    return value


def serialize_timedelta(interval: timedelta) -> str:
    """Serialize timedelta."""

    seconds = interval.total_seconds()
    if seconds <= 0:
        return "0s"

    dt_string = ""
    if seconds > 3600:  # noqa: PLR2004
        hours = int(seconds // 3600)
        dt_string += f"{hours}h"
        seconds -= hours * 3600
    if seconds > 60:  # noqa: PLR2004
        minutes = int(seconds // 60)
        dt_string += f"{minutes}m"
        seconds -= minutes * 60
    if seconds > 0:
        dt_string += f"{int(seconds)}s"
    return dt_string


def human_format(interval: float | timedelta) -> str:
    """Get humand readable format for interval."""

    if isinstance(interval, int | float):
        interval = timedelta(seconds=interval)

    return time_delta(interval)


@lru_cache(maxsize=20)
def notify_intervals(interval: timedelta) -> list[int]:
    """Intervals to notify players."""

    seconds = int(interval.total_seconds())
    if seconds <= 0:
        return []

    intervals = [seconds]
    if seconds > _INTERVALS["1h"]:
        intervals.append(_INTERVALS["1h"])
    if seconds > _INTERVALS["30m"]:
        intervals.append(_INTERVALS["30m"])
    if seconds > _INTERVALS["5m"]:
        intervals.append(_INTERVALS["5m"])
    if seconds > _INTERVALS["1m"]:
        intervals.append(_INTERVALS["1m"])
    if seconds > _INTERVALS["30s"]:
        intervals.append(_INTERVALS["30s"])
    if seconds > _INTERVALS["10s"]:
        intervals.append(_INTERVALS["10s"])

    return intervals
