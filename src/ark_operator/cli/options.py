"""ARK Operator CLI options."""

from pathlib import Path
from typing import Annotated

from cyclopts import Parameter

from ark_operator.log import LoggingFormat, LoggingLevel

OPTION_LOG_FORMAT = Annotated[LoggingFormat, Parameter(env_var="ARK_OP_LOG_FORMAT")]
OPTION_LOG_LEVEL = Annotated[LoggingLevel, Parameter(env_var="ARK_OP_LOG_LEVEL")]

OPTION_INSTALL_DIR = Annotated[
    Path,
    Parameter(
        ("--install-dir", "-d"),
        env_var=["ARK_SERVER_DIR", "ARK_SERVER_A_DIR"],
    ),
]

OPTION_STEAM_DIR = Annotated[
    Path,
    Parameter(
        ("--steam-dir", "-s"),
        env_var="ARK_STEAM_DIR",
    ),
]

OPTION_COPY_DIR = Annotated[
    Path | None,
    Parameter(
        ("--copy-from"),
        env_var=["ARK_SERVER_B_DIR"],
    ),
]

OPTION_IP = Annotated[
    str,
    Parameter(
        ("--ip", "-h"),
        env_var=["ARK_SERVER_IP"],
    ),
]

OPTION_RCON_PORT = Annotated[
    int,
    Parameter(
        ("--rcon-port"),
        env_var=["ARK_SERVER_RCON_PORT"],
    ),
]

OPTION_RCON_PASSWORD = Annotated[
    str,
    Parameter(
        ("--rcon-password"),
        env_var=["ARK_SERVER_RCON_PASSWORD"],
    ),
]