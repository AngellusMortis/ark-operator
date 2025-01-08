"""ARK Server CLI."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Annotated, cast

from aiofiles import os as aos
from cyclopts import App, Parameter

from ark_operator.ark import ArkServer
from ark_operator.cli.context import ServerContext, get_all_context, set_context
from ark_operator.cli.options import (
    OPTION_COPY_DIR,
    OPTION_DATA_DIR,
    OPTION_DRY_RUN,
    OPTION_GAME_PORT,
    OPTION_HOST,
    OPTION_INSTALL_DIR,
    OPTION_RCON_PASSWORD,
    OPTION_RCON_PORT,
    OPTION_SERVER_ALLOWED_PLATFORMS,
    OPTION_SERVER_BATTLEYE,
    OPTION_SERVER_CLUSTER_ID,
    OPTION_SERVER_MAP,
    OPTION_SERVER_MAX_PLAYERS,
    OPTION_SERVER_MULTIHOME_IP,
    OPTION_SERVER_SESSION_NAME,
    OPTION_SERVER_WHITELIST,
    OPTION_STEAM_DIR,
)
from ark_operator.rcon import send_cmd
from ark_operator.steam import Steam

if TYPE_CHECKING:
    from ipaddress import IPv4Address, IPv6Address

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
def meta(  # noqa: PLR0913
    *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
    install_dir: OPTION_INSTALL_DIR,
    data_dir: OPTION_DATA_DIR,
    steam_dir: OPTION_STEAM_DIR,
    host: OPTION_HOST,
    rcon_password: OPTION_RCON_PASSWORD,
    map_name: OPTION_SERVER_MAP,
    session_name: OPTION_SERVER_SESSION_NAME,
    rcon_port: OPTION_RCON_PORT = 27020,
    game_port: OPTION_GAME_PORT = 7777,
    multihome_ip: OPTION_SERVER_MULTIHOME_IP = None,
    max_players: OPTION_SERVER_MAX_PLAYERS = 70,
    cluster_id: OPTION_SERVER_CLUSTER_ID = "ark-cluster",
    battleye: OPTION_SERVER_BATTLEYE = True,
    allowed_platforms: OPTION_SERVER_ALLOWED_PLATFORMS = None,
    whitelist: OPTION_SERVER_WHITELIST = False,
) -> int | None:
    """
    ARK Server CLI.

    Helpful commands for managing an ARK: Survival Ascended server.
    """

    install_dir = install_dir.absolute()
    steam_dir = steam_dir.absolute()
    set_context(
        "server",
        ServerContext(
            install_dir=install_dir,
            data_dir=data_dir,
            steam_dir=steam_dir,
            steam=Steam(install_dir=steam_dir),
            host=host,
            rcon_port=rcon_port,
            rcon_password=rcon_password,
            game_port=game_port,
            map_name=map_name,
            session_name=session_name,
            multihome_ip=multihome_ip,
            max_players=max_players,
            cluster_id=cluster_id,
            battleye=battleye,
            allowed_platforms=allowed_platforms or ["ALL"],
            whitelist=whitelist,
            parent=get_all_context("core"),  # type: ignore[arg-type]
        ),
    )
    return server(tokens)  # type: ignore[no-any-return]


@server.command
async def install(
    *,
    validate: bool = True,
    copy_from: OPTION_COPY_DIR = None,
    dry_run: OPTION_DRY_RUN = False,
) -> None:
    """Install ARK: Survival Ascended Server."""

    context = _get_context()
    if copy_from:
        copy_from = copy_from.absolute()
        _LOGGER.info("Copy ARK from %s to ARK at %s", copy_from, context.install_dir)
        await context.steam.copy_ark(copy_from, context.install_dir, dry_run=dry_run)

    has_newer = await context.steam.has_newer_version(context.install_dir)
    _LOGGER.info(
        "ARK has newer version: %s",
        has_newer,
    )
    if not has_newer and not validate:
        _LOGGER.info(
            "Skipping install since there is no new version and validate is disabled"
        )
    else:
        _LOGGER.info("Installing ARK at %s", context.install_dir)
        await context.steam.install_ark(
            context.install_dir, validate=validate, dry_run=dry_run
        )


async def _run_command(
    cmd: str, *, host: IPv4Address | IPv6Address | str | None = None, close: bool = True
) -> None:
    context = _get_context()

    host = host or context.host
    _LOGGER.info("%s:%s - %s", host, context.rcon_port, cmd)
    response = await send_cmd(
        cmd,
        host=host,
        port=context.rcon_port,
        password=context.rcon_password,
        close=close,
    )
    _LOGGER.info(response)


async def _do_shutdown(host: str | None = None) -> None:
    await _run_command("SaveWorld", close=False, host=host)
    await _run_command("DoExit", host=host)


@server.command
async def rcon(*cmd: str) -> None:
    """Run rcon command for ARK server."""

    await _run_command(" ".join(cmd))


@server.command
async def save() -> None:
    """Run save rcon command for ARK server."""

    await _run_command("SaveWorld")


@server.command
async def broadcast(*message: str) -> None:
    """Run send message via rcon to ARK server."""

    await _run_command(f"ServerChat {" ".join(message)}")


@server.command
async def shutdown() -> None:
    """Run shutdown server via rcon."""

    await _do_shutdown()


@server.command
async def run(*, dry_run: OPTION_DRY_RUN = False) -> None:
    """Run ARK server."""

    context = _get_context()
    server = ArkServer(
        server_dir=context.install_dir.parent,
        data_dir=context.data_dir,
        map_name=context.map_name,
        session_name=context.session_name,
        rcon_port=context.rcon_port,
        rcon_password=context.rcon_password,
        game_port=context.game_port,
        max_players=context.max_players,
        cluster_id=context.cluster_id,
        battleye=context.battleye,
        allowed_platforms=context.allowed_platforms,
        whitelist=context.whitelist,
        multihome_ip=context.multihome_ip,
    )
    try:
        await asyncio.shield(server.run(dry_run=dry_run))
    except asyncio.CancelledError:
        _LOGGER.info("Shutting down server...")
        await _do_shutdown(host="127.0.0.1")

    if await aos.path.exists(server.marker_file):
        await aos.remove(server.marker_file)
