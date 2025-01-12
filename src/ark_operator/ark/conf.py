"""ARK config parser."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, overload

from aiofiles import open as aopen

if TYPE_CHECKING:
    from pathlib import Path


_LOGGER = logging.getLogger(__name__)


async def read_config(path: Path) -> dict[str, dict[str, str]]:
    """Read ARK config file."""

    conf: dict[str, dict[str, str]] = {}
    async with aopen(path) as f:
        section = None
        for line in await f.readlines():
            line = line.strip()  # noqa: PLW2901
            if line.startswith("[") and line.endswith("]"):
                section = line.lstrip("[").rstrip("]")
                conf[section] = {}
                continue

            key, value = line.split("=")
            conf[section or ""][key.strip()] = value.strip()

    return conf


async def write_config(conf: dict[str, dict[str, str]], path: Path) -> None:
    """Write ARK config file."""

    async with aopen(path, "w") as f:
        first_section = True
        if "" in conf:
            for key, value in conf.pop("None").items():
                await f.write(f"{key} = {value}\n")

        for section, values in conf.items():
            if first_section:
                first_section = False
            else:
                await f.write("\n")
            await f.write(f"[{section}]\n")

            for key, value in values.items():
                await f.write(f"{key} = {value}\n")


@overload
def merge_conf(
    parent: dict[str, dict[str, str]],
    child: dict[str, dict[str, str]] | None,
    *,
    warn: bool = False,
) -> dict[str, dict[str, str]]: ...  # pragma: no cover


@overload
def merge_conf(
    parent: dict[str, dict[str, str]] | None,
    child: dict[str, dict[str, str]],
    *,
    warn: bool = False,
) -> dict[str, dict[str, str]]: ...  # pragma: no cover


@overload
def merge_conf(
    parent: None, child: None, *, warn: bool = False
) -> None: ...  # pragma: no cover


@overload
def merge_conf(
    parent: dict[str, dict[str, str]] | None,
    child: dict[str, dict[str, str]] | None,
    *,
    warn: bool = False,
) -> dict[str, dict[str, str]] | None: ...  # pragma: no cover


def merge_conf(
    parent: dict[str, dict[str, str]] | None,
    child: dict[str, dict[str, str]] | None,
    *,
    warn: bool = False,
) -> dict[str, dict[str, str]] | None:
    """Merge two ARK configs."""

    if parent is None and child is None:
        _LOGGER.debug("No configs to merge")
        return None

    if parent is None:
        _LOGGER.debug("No parent config to merge")
        return child

    if child is None:  # pragma: no cover
        _LOGGER.debug("No child config to merge")
        return parent

    for section, values in child.items():
        if section not in parent:
            parent[section] = {}

        for key, value in values.items():
            old_value = parent[section].get(key, value)
            if value != old_value:
                _log = _LOGGER.debug
                if warn:
                    _log = _LOGGER.warning
                _log(
                    "key %s: child value (%s) overwriting parent value (%s)",
                    key,
                    value,
                    old_value,
                )
            parent[section][key] = value

    return parent
