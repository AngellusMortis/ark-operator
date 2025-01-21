"""ARK Operator CLI options."""

from __future__ import annotations

from datetime import timedelta
from ipaddress import IPv4Address, IPv6Address
from pathlib import Path
from typing import Annotated, Any, Literal

from cyclopts import Parameter

from ark_operator.cli.converters import timedelta_converter
from ark_operator.data import ArkClusterSpec
from ark_operator.log import LoggingFormat, LoggingLevel

OPTION_LOG_FORMAT = Annotated[LoggingFormat, Parameter(env_var="ARK_OP_LOG_FORMAT")]
OPTION_LOG_LEVEL = Annotated[LoggingLevel, Parameter(env_var="ARK_OP_LOG_LEVEL")]
OPTION_LOG_CONFIG = Annotated[dict[str, Any], Parameter(env_var="ARK_OP_LOG_CONFIG")]
OPTION_DRY_RUN = Annotated[bool, Parameter(env_var="ARK_OP_DRY_RUN")]

OPTION_INSTALL_DIR = Annotated[
    Path | None,
    Parameter(
        ("--install-dir", "-i"),
        env_var=["ARK_SERVER_DIR", "ARK_SERVER_A_DIR"],
    ),
]

OPTION_DATA_DIR = Annotated[
    Path | None,
    Parameter(
        ("--data-dir", "-d"),
        env_var=["ARK_DATA_DIR"],
    ),
]

OPTION_STEAM_DIR = Annotated[
    Path | None,
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
        ("--host"),
        env_var=["ARK_SERVER_HOST"],
    ),
]

OPTION_HOST = Annotated[
    IPv4Address | IPv6Address | str | None,
    Parameter(
        ("--host"),
        env_var=["ARK_SERVER_HOST"],
    ),
]

OPTION_GAME_PORT = Annotated[
    int,
    Parameter(
        ("-p", "--game-port"),
        env_var=["ARK_SERVER_GAME_PORT"],
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

OPTION_RCON_PASSWORD_OPTIONAL = Annotated[
    str | None,
    Parameter(
        ("--rcon-password"),
        env_var=["ARK_SERVER_RCON_PASSWORD"],
    ),
]

OPTION_ARK_CLUSTER_NAME = Annotated[
    str, Parameter(("--name"), env_var=["ARK_CLUSTER_NAME"])
]

OPTION_ARK_CLUSTER_NAMESPACE = Annotated[
    str, Parameter(("--namespace"), env_var=["ARK_CLUSTER_NAMESPACE"])
]

OPTION_ARK_SPEC = Annotated[
    ArkClusterSpec | None,
    Parameter(("--spec"), env_var=["ARK_CLUSTER_SPEC"]),
]

OPTION_ARK_STATUS = Annotated[
    str | None,
    Parameter(("--status"), env_var=["ARK_CLUSTER_STATUS"]),
]

OPTION_MAPS = Annotated[
    list[
        Literal["@canonical", "@canonicalNoClub", "@official", "@officialNoClub"] | str  # noqa: PYI051
    ]
    | None,
    Parameter(("-m", "--maps")),
]

OPTION_ARK_SELECTOR = Annotated[
    list[Literal["@all"] | str],  # noqa: PYI051
    Parameter("--selector"),
]

OPTION_SERVER_MAP = Annotated[
    str | None, Parameter(("-m", "--map"), env_var=["ARK_SERVER_MAP"])
]

OPTION_SERVER_SESSION_NAME = Annotated[
    str | None, Parameter(("-n", "--session-name"), env_var=["ARK_SERVER_SESSION_NAME"])
]

OPTION_SERVER_MULTIHOME_IP = Annotated[
    str | None, Parameter("--multihome-ip", env_var=["ARK_SERVER_MULTIHOME"])
]

OPTION_SERVER_MAX_PLAYERS = Annotated[
    int, Parameter("--max-players", env_var=["ARK_SERVER_MAX_PLAYERS"])
]

OPTION_SERVER_CLUSTER_ID = Annotated[
    str, Parameter("--cluster-id", env_var=["ARK_SERVER_CLUSTER_ID"])
]

OPTION_SERVER_BATTLEYE = Annotated[
    bool, Parameter("--battleye", env_var=["ARK_SERVER_BATTLEYE"])
]

OPTION_SERVER_ALLOWED_PLATFORMS = Annotated[
    list[Literal["ALL", "PS5", "XSX", "PC", "WINGDK"]] | None,
    Parameter("--allowed-platforms", env_var=["ARK_SERVER_ALLOWED_PLATFORMS"]),
]

OPTION_SERVER_WHITELIST = Annotated[
    bool, Parameter("--whitelist", env_var=["ARK_SERVER_WHITELIST"])
]

OPTION_SERVER_PARAM = Annotated[
    list[str] | None, Parameter("--param", env_var=["ARK_SERVER_PARAMS"])
]

OPTION_SERVER_OPT = Annotated[
    list[str] | None, Parameter("--opt", env_var=["ARK_SERVER_OPTS"])
]

OPTION_SERVER_MODS = Annotated[
    list[str] | None, Parameter("--mod", env_var=["ARK_SERVER_MODS"])
]

OPTION_SERVER_GLOBAL_GUS = Annotated[
    Path | None, Parameter("--global-gus", env_var=["ARK_SERVER_GLOBAL_GUS"])
]

OPTION_SERVER_GLOBAL_GUS_SECRETS = Annotated[
    str | None,
    Parameter("--global-gus-secrets", env_var=["ARK_SERVER_GLOBAL_GUS_SECRETS"]),
]

OPTION_SERVER_MAP_GUS = Annotated[
    Path | None, Parameter("--map-gus", env_var=["ARK_SERVER_MAP_GUS"])
]

OPTION_SERVER_GLOBAL_GAME = Annotated[
    Path | None, Parameter("--global-game", env_var=["ARK_SERVER_GLOBAL_GAME"])
]

OPTION_SERVER_MAP_GAME = Annotated[
    Path | None, Parameter("--map-game", env_var=["ARK_SERVER_MAP_GAME"])
]

OPTION_WAIT_INTERVAL = Annotated[
    timedelta | None, Parameter(converter=timedelta_converter)
]
