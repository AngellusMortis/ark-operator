"""ARK Operator CLI contexts."""

from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address
from pathlib import Path
from typing import Any, Literal

from ark_operator.data import ArkClusterSpec
from ark_operator.log import LoggingFormat, LoggingLevel
from ark_operator.steam import Steam

_CONTEXT: dict[str, Any] = {}


def set_context(name: str, data: Any) -> None:  # noqa: ANN401
    """Set CLI context."""

    _CONTEXT[name] = data


def get_all_context(name: str) -> Any | None:  # noqa: ANN401
    """Get CLI context."""

    return _CONTEXT.get(name)


@dataclass
class CoreContext:
    """Core commands context object."""

    logging_format: LoggingFormat
    logging_level: LoggingLevel


@dataclass
class ServerContext:
    """Server commands context object."""

    install_dir: Path
    data_dir: Path
    steam_dir: Path
    steam: Steam
    host: IPv4Address | IPv6Address | str
    rcon_port: int
    rcon_password: str
    game_port: int
    map_name: str
    session_name: str
    multihome_ip: str | None
    max_players: int
    cluster_id: str
    battleye: bool
    allowed_platforms: list[Literal["ALL", "PS5", "XSX", "PC", "WINGDK"]]
    whitelist: bool
    parameters: list[str]
    options: list[str]
    mods: list[str]

    parent: CoreContext


@dataclass
class ClusterContext:
    """Cluster commands context object."""

    spec: ArkClusterSpec
    selected_maps: list[str]
    host: IPv4Address | IPv6Address | str
    rcon_password: str

    parent: CoreContext
