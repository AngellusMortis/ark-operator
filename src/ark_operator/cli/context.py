"""ARK Operator CLI contexts."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ark_operator.data import Steam
from ark_operator.log import LoggingFormat, LoggingLevel

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
    """Core commands context object."""

    install_dir: Path
    steam_dir: Path
    steam: Steam
    ip: str
    rcon_port: int
    rcon_password: str

    parent: CoreContext
