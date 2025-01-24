"""CurseForge interface."""

from __future__ import annotations

from datetime import datetime

import httpx
from environs import Env

_CLIENT: httpx.AsyncClient | None = None
_ENV = Env()

ERROR_NO_AUTH = "No CurseForge API key provided."
ERROR_NO_FILES = "Mod has no files."


def get_cf_auth() -> str | None:
    """Get CurseForge auth."""

    return _ENV("ARK_OP_CURSEFORGE_API_KEY", None)


def has_cf_auth() -> bool:
    """Check if CurseForge auth exists."""

    return get_cf_auth() is None


async def get_cf_client() -> httpx.AsyncClient:
    """Get http client for CurseForge."""

    global _CLIENT  # noqa: PLW0603

    api_key = get_cf_auth()
    if not api_key:
        raise RuntimeError(ERROR_NO_AUTH)

    if _CLIENT is None:
        _CLIENT = httpx.AsyncClient(headers={"x-api-key": api_key})
        await _CLIENT.__aenter__()

    return _CLIENT


async def close_cf_client() -> None:
    """Close http client for CurseForge."""

    global _CLIENT  # noqa: PLW0603

    if _CLIENT is not None:
        await _CLIENT.__aexit__()
        _CLIENT = None


async def get_mod_lastest_update(mod_id: str) -> tuple[str, datetime]:
    """Get latest update time for mod."""

    client = await get_cf_client()
    response = await client.get(f"https://api.curseforge.com/v1/mods/{mod_id}")
    response.raise_for_status()

    data = response.json()
    if (
        "data" not in data
        or "latestFiles" not in data["data"]
        or not data["data"]["latestFiles"]
    ):
        raise RuntimeError(ERROR_NO_FILES)

    latest_file = data["data"]["latestFiles"][0]
    return data["data"]["name"], datetime.fromisoformat(latest_file["fileDate"])
