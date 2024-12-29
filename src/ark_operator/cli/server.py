"""ARK Operator CLI."""

import logging
from typing import Annotated, cast

from cyclopts import App, Parameter

from ark_operator.cli.context import ServerContext, get_all_context, set_context
from ark_operator.cli.options import (
    OPTION_COPY_DIR,
    OPTION_INSTALL_DIR,
    OPTION_IP,
    OPTION_RCON_PASSWORD,
    OPTION_RCON_PORT,
    OPTION_STEAM_DIR,
)
from ark_operator.data import Steam
from ark_operator.rcon import send_cmd

server = App(
    help="""
    ARK Server CLI.

    Helpful commands for managing an ARK: Survival Ascended server.
"""
)

_LOGGER = logging.getLogger(__name__)


def _get_context() -> ServerContext:
    return cast(ServerContext, get_all_context("server"))


@server.meta.default
def meta(
    *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
    install_dir: OPTION_INSTALL_DIR,
    steam_dir: OPTION_STEAM_DIR,
    ip: OPTION_IP,
    rcon_port: OPTION_RCON_PORT,
    rcon_password: OPTION_RCON_PASSWORD,
) -> None:
    """ARK Operator."""

    set_context(
        "server",
        ServerContext(
            install_dir=install_dir,
            steam_dir=steam_dir,
            steam=Steam.create(install_dir=steam_dir),
            ip=ip,
            rcon_port=rcon_port,
            rcon_password=rcon_password,
            parent=get_all_context("core"),  # type: ignore[arg-type]
        ),
    )
    server(tokens)


@server.command
def install(*, validate: bool = True, copy_from: OPTION_COPY_DIR = None) -> None:
    """Install ARK: Survival Ascended Server."""

    context = _get_context()
    if copy_from:
        _LOGGER.info("Copy ARK from %s to ARK at %s", copy_from, context.install_dir)
        context.steam.copy_ark(copy_from, context.install_dir)

    _LOGGER.info("Installing ARK at %s", context.install_dir)
    context.steam.install_ark(context.install_dir, validate=validate)


@server.command
async def rcon(cmd: str) -> None:
    """Run rcon command for ARK server."""

    context = _get_context()

    _LOGGER.info("%s:%s - %s", context.ip, context.rcon_port, cmd)
    response = await send_cmd(
        cmd, host=context.ip, port=context.rcon_port, password=context.rcon_password
    )
    _LOGGER.info(response)
