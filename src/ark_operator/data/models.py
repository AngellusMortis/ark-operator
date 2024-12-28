"""ARK Operator config."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path  # required for Pydantic # noqa: TC003

from pydantic_settings import BaseSettings
from pysteamcmdwrapper import SteamCMD

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=r"invalid escape sequence '\\-'")
    warnings.filterwarnings("ignore", message=r"invalid escape sequence '\\\('")
    warnings.filterwarnings("ignore", message=r"invalid escape sequence '\\d'")
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    from steam.client import SteamClient
    from steam.client.cdn import CDNClient


class Config(BaseSettings):
    """ARK Operator config."""

    steam_install_dir: Path
    ark_a_install_dir: Path
    ark_b_install_dir: Path


@dataclass
class Steam:
    """Steam wrapper."""

    cmd: SteamCMD
    api: SteamClient
    cdn: CDNClient

    @classmethod
    def create(cls, *, install_dir: Path) -> Steam:
        """Create Steam obj."""

        steam = SteamClient()
        steam.anonymous_login()
        cdn = CDNClient(steam)

        return Steam(cmd=SteamCMD(install_dir), api=steam, cdn=cdn)
