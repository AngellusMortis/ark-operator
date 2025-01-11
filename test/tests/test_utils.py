"""Test utils."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from aiofiles import os as aos

from ark_operator.utils import comma_list, ensure_symlink, touch_file

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
