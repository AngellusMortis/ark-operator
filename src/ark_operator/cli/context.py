"""ARK Operator CLI contexts."""

from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address
from pathlib import Path
from typing import Any

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
    steam_dir: Path
    steam: Steam
    ip: IPv4Address | IPv6Address
    rcon_port: int
    rcon_password: str

    parent: CoreContext


@dataclass
class ClusterContext:
    """Cluster commands context object."""

    spec: ArkClusterSpec
    map_selector: list[str]
    ip: IPv4Address | IPv6Address
    rcon_password: str

    parent: CoreContext
