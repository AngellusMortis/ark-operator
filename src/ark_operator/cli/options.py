"""ARK Operator CLI options."""

from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address
from pathlib import Path
from typing import Annotated, Any, Literal

from cyclopts import Parameter

from ark_operator.data import ArkClusterSpec
from ark_operator.log import LoggingFormat, LoggingLevel

OPTION_LOG_FORMAT = Annotated[LoggingFormat, Parameter(env_var="ARK_OP_LOG_FORMAT")]
OPTION_LOG_LEVEL = Annotated[LoggingLevel, Parameter(env_var="ARK_OP_LOG_LEVEL")]
OPTION_LOG_CONFIG = Annotated[dict[str, Any], Parameter(env_var="ARK_OP_LOG_CONFIG")]
OPTION_DRY_RUN = Annotated[bool, Parameter(env_var="ARK_OP_DRY_RUN")]

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

OPTION_OPTIONAL_HOST = Annotated[
    IPv4Address | IPv6Address | str | None,
    Parameter(
        ("--host", "-h"),
        env_var=["ARK_SERVER_HOST"],
    ),
]

OPTION_HOST = Annotated[
    IPv4Address | IPv6Address | str,
    Parameter(
        ("--host", "-h"),
        env_var=["ARK_SERVER_HOST"],
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

OPTION_ARK_SPEC = Annotated[
    ArkClusterSpec,
    Parameter(("--spec"), env_var=["ARK_CLUSTER_SPEC"]),
]

OPTION_MAPS = Annotated[
    list[
        Literal["@canonical", "@canonicalNoClub", "@official", "@officialNoClub"] | str  # noqa: PYI051
    ]
    | None,
    Parameter("-m", "--maps"),
]

OPTION_ARK_SELECTOR = Annotated[
    list[Literal["@all"] | str],  # noqa: PYI051
    Parameter("--selector"),
]
