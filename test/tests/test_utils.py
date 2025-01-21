"""Test utils."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from aiofiles import os as aos

from ark_operator.utils import (
    comma_list,
    convert_timedelta,
    ensure_symlink,
    human_format,
    notify_intervals,
    serialize_timedelta,
    touch_file,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_ensure_symlink(temp_dir: Path) -> None:
    """Test ensure_symlink."""

    await aos.makedirs(temp_dir / "dir", exist_ok=True)
    await aos.makedirs(temp_dir / "dir2", exist_ok=True)
    await touch_file(temp_dir / "test.txt")
    await touch_file(temp_dir / "test2.txt")

    await ensure_symlink(temp_dir / "dir", temp_dir / "link")
    assert await aos.path.islink(temp_dir / "link")
    assert await aos.readlink(str(temp_dir / "link")) == str(temp_dir / "dir")

    await ensure_symlink(temp_dir / "dir", temp_dir / "link")
    assert await aos.path.islink(temp_dir / "link")
    assert await aos.readlink(str(temp_dir / "link")) == str(temp_dir / "dir")

    await ensure_symlink(temp_dir / "dir2", temp_dir / "link")
    assert await aos.path.islink(temp_dir / "link")
    assert await aos.readlink(str(temp_dir / "link")) == str(temp_dir / "dir2")

    await ensure_symlink(temp_dir / "dir", temp_dir / "dir2")
    assert not await aos.path.islink(temp_dir / "dir2")

    await ensure_symlink(temp_dir / "test.txt", temp_dir / "test2.txt", is_dir=False)
    assert await aos.path.islink(temp_dir / "test2.txt")


@pytest.mark.parametrize(
    ("in_", "out"),
    [
        (None, None),
        (["1", "2", "3"], ["1", "2", "3"]),
        (["1"], ["1"]),
        (["1,2,3"], ["1", "2", "3"]),
    ],
)
def test_comma_list(in_: list[str] | None, out: list[str] | None) -> None:
    """Test comma_list."""

    assert comma_list(in_) == out


@pytest.mark.parametrize(
    ("in_", "out"),
    [
        ("nomatch", "nomatch"),
        (0, timedelta(seconds=0)),
        (100, timedelta(minutes=1, seconds=40)),
        ("3h", timedelta(hours=3)),
        ("5m", timedelta(minutes=5)),
        ("30s", timedelta(seconds=30)),
        ("1m40s", timedelta(minutes=1, seconds=40)),
        ("5h40s", timedelta(hours=5, seconds=40)),
        ("5h1m40s", timedelta(hours=5, minutes=1, seconds=40)),
    ],
)
def test_convert_timedelta(in_: str | int, out: str) -> None:
    """Test convert_timedelta."""

    assert convert_timedelta(in_) == out


@pytest.mark.parametrize(
    ("out", "in_"),
    [
        ("0s", timedelta(seconds=0)),
        ("3h", timedelta(hours=3)),
        ("5m", timedelta(minutes=5)),
        ("30s", timedelta(seconds=30)),
        ("1m40s", timedelta(minutes=1, seconds=40)),
        ("5h40s", timedelta(hours=5, seconds=40)),
        ("5h1m40s", timedelta(hours=5, minutes=1, seconds=40)),
    ],
)
def test_serialize_timedelta(in_: timedelta, out: str) -> None:
    """Test serialize_timedelta."""

    assert serialize_timedelta(in_) == out


@pytest.mark.parametrize(
    ("in_", "out"),
    [
        (100, "a minute"),
        (timedelta(hours=3), "3 hours"),
        (timedelta(minutes=5), "5 minutes"),
        (timedelta(seconds=30), "30 seconds"),
        (timedelta(minutes=1, seconds=40), "a minute"),
        (timedelta(hours=5, seconds=40), "5 hours"),
        (timedelta(hours=5, minutes=1, seconds=40), "5 hours"),
    ],
)
def test_human_format(in_: float | timedelta, out: str) -> None:
    """Test human_format."""

    assert human_format(in_) == out


@pytest.mark.parametrize(
    ("in_", "out"),
    [
        (timedelta(hours=3), [3600 * 3, 3600, 1800, 300, 60, 30, 10]),
        (timedelta(hours=1), [3600, 1800, 300, 60, 30, 10]),
        (timedelta(minutes=40), [2400, 1800, 300, 60, 30, 10]),
        (timedelta(minutes=30), [1800, 300, 60, 30, 10]),
        (timedelta(minutes=20), [1200, 300, 60, 30, 10]),
        (timedelta(minutes=10), [600, 300, 60, 30, 10]),
        (timedelta(minutes=5), [300, 60, 30, 10]),
        (timedelta(minutes=1), [60, 30, 10]),
        (timedelta(seconds=40), [40, 30, 10]),
        (timedelta(seconds=30), [30, 10]),
        (timedelta(seconds=20), [20, 10]),
        (timedelta(seconds=10), [10]),
        (timedelta(seconds=0), []),
    ],
)
def test_notify_intervals(in_: timedelta, out: list[int]) -> None:
    """Test notify_intervals."""

    assert notify_intervals(in_) == out
