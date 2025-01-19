"""ARK Server CLI."""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import TYPE_CHECKING, Annotated, Any, cast

from aiofiles import os as aos
from cyclopts import App, CycloptsError, Parameter

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
    OPTION_SERVER_GLOBAL_GAME,
    OPTION_SERVER_GLOBAL_GUS,
    OPTION_SERVER_MAP,
    OPTION_SERVER_MAP_GAME,
    OPTION_SERVER_MAP_GUS,
    OPTION_SERVER_MAX_PLAYERS,
    OPTION_SERVER_MODS,
    OPTION_SERVER_MULTIHOME_IP,
    OPTION_SERVER_OPT,
    OPTION_SERVER_PARAM,
    OPTION_SERVER_SESSION_NAME,
    OPTION_SERVER_WHITELIST,
    OPTION_STEAM_DIR,
)
from ark_operator.rcon import send_cmd
from ark_operator.steam import Steam
from ark_operator.utils import comma_list

if TYPE_CHECKING:
    from ipaddress import IPv4Address, IPv6Address
    from pathlib import Path

server = App(
    help="""
    ARK Server CLI.

    Helpful commands for managing an ARK: Survival Ascended server.
"""
)

_LOGGER = logging.getLogger(__name__)
ERROR_FIELD_REQUIRED = "Error option {name} is required"
ERROR_RUN_SERVER = "Error running server"


def _get_context() -> ServerContext:
    return cast(ServerContext, get_all_context("server"))


def _require_steam() -> Steam:
    context = _get_context()
    if context.steam is None:
        raise CycloptsError(msg=ERROR_FIELD_REQUIRED.format(name="steam_dir"))

    return context.steam


def _require_install_dir() -> Path:
    context = _get_context()
    if context.install_dir is None:
        raise CycloptsError(msg=ERROR_FIELD_REQUIRED.format(name="install_dir"))

    return context.install_dir


def _require_host() -> IPv4Address | IPv6Address | str:
    context = _get_context()
    if context.host is None:
        raise CycloptsError(msg=ERROR_FIELD_REQUIRED.format(name="host"))

    return context.host


def _require_data_dir() -> Path:
    context = _get_context()
    if context.data_dir is None:
        raise CycloptsError(msg=ERROR_FIELD_REQUIRED.format(name="data_dir"))

    return context.data_dir


def _require_map_name() -> str:
    context = _get_context()
    if context.map_name is None:
        raise CycloptsError(msg=ERROR_FIELD_REQUIRED.format(name="map_name"))

    return context.map_name


def _require_session_name() -> str:
    context = _get_context()
    if context.session_name is None:
        raise CycloptsError(msg=ERROR_FIELD_REQUIRED.format(name="session_name"))

    return context.session_name


@server.meta.default
def meta(  # noqa: PLR0913
    *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
    rcon_password: OPTION_RCON_PASSWORD,
    host: OPTION_HOST = None,
    map_name: OPTION_SERVER_MAP = None,
    session_name: OPTION_SERVER_SESSION_NAME = None,
    install_dir: OPTION_INSTALL_DIR = None,
    data_dir: OPTION_DATA_DIR = None,
    steam_dir: OPTION_STEAM_DIR = None,
    rcon_port: OPTION_RCON_PORT = 27020,
    game_port: OPTION_GAME_PORT = 7777,
    multihome_ip: OPTION_SERVER_MULTIHOME_IP = None,
    max_players: OPTION_SERVER_MAX_PLAYERS = 70,
    cluster_id: OPTION_SERVER_CLUSTER_ID = "ark-cluster",
    battleye: OPTION_SERVER_BATTLEYE = True,
    allowed_platforms: OPTION_SERVER_ALLOWED_PLATFORMS = None,
    whitelist: OPTION_SERVER_WHITELIST = False,
    parameters: OPTION_SERVER_PARAM = None,
    options: OPTION_SERVER_OPT = None,
    mods: OPTION_SERVER_MODS = None,
    global_gus: OPTION_SERVER_GLOBAL_GUS = None,
    map_gus: OPTION_SERVER_MAP_GUS = None,
    global_game: OPTION_SERVER_GLOBAL_GAME = None,
    map_game: OPTION_SERVER_MAP_GAME = None,
) -> int | None:
    """
    ARK Server CLI.

    Helpful commands for managing an ARK: Survival Ascended server.
    """

    mods = comma_list(mods)
    allowed_platforms = comma_list(allowed_platforms)  # type: ignore[assignment,arg-type]
    parameters = comma_list(parameters)
    options = comma_list(options)
    install_dir = install_dir.absolute() if install_dir else None
    steam_dir = steam_dir.absolute() if steam_dir else None

    set_context(
        "server",
        ServerContext(
            install_dir=install_dir,
            data_dir=data_dir,
            steam_dir=steam_dir,
            steam=Steam(install_dir=steam_dir) if steam_dir else None,
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
            parameters=parameters or [],
            options=options or [],
            mods=mods or [],
            global_gus=global_gus,
            map_gus=map_gus,
            global_game=global_game,
            map_game=map_game,
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

    steam = _require_steam()
    install_dir = _require_install_dir()

    if copy_from:
        copy_from = copy_from.absolute()
        _LOGGER.info("Copy ARK from %s to ARK at %s", copy_from, install_dir)
        await steam.copy_ark(copy_from, install_dir, dry_run=dry_run)

    has_newer = await steam.has_newer_version(install_dir)
    _LOGGER.info(
        "ARK has newer version: %s",
        has_newer,
    )
    if not has_newer and not validate:
        _LOGGER.info(
            "Skipping install since there is no new version and validate is disabled"
        )
    else:
        _LOGGER.info("Installing ARK at %s", install_dir)
        await steam.install_ark(install_dir, validate=validate, dry_run=dry_run)


async def _run_command(
    cmd: str, *, host: IPv4Address | IPv6Address | str | None = None, close: bool = True
) -> None:
    context = _get_context()

    host = host or _require_host()
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

    await _run_command(f"ServerChat {' '.join(message)}")


@server.command
async def shutdown() -> None:
    """Run shutdown server via rcon."""

    await _do_shutdown()


async def _run_server(*, dry_run: bool, immutable: bool) -> Path:
    context = _get_context()
    server = ArkServer(
        server_dir=_require_install_dir().parent,
        data_dir=_require_data_dir(),
        map_name=_require_map_name(),
        session_name=_require_session_name(),
        rcon_port=context.rcon_port,
        rcon_password=context.rcon_password,
        game_port=context.game_port,
        max_players=context.max_players,
        cluster_id=context.cluster_id,
        battleye=context.battleye,
        allowed_platforms=context.allowed_platforms,
        whitelist=context.whitelist,
        multihome_ip=context.multihome_ip,
        parameters=context.parameters,
        options=context.options,
        mods=context.mods,
        global_config=context.global_gus,
        map_config=context.map_gus,
        global_ark_config=context.global_game,
        map_ark_config=context.map_game,
    )

    try:
        await server.run(dry_run=dry_run, read_only=immutable)
    except Exception:
        _LOGGER.exception(ERROR_RUN_SERVER)

    return server.marker_file


async def _shutdown(event: asyncio.Event, task: asyncio.Task[Any]) -> None:
    try:
        await asyncio.shield(event.wait())
    except asyncio.CancelledError:
        await event.wait()

    _LOGGER.info("Shutting down server...")
    retries = 10
    while retries > 0:
        try:
            await _do_shutdown(host="127.0.0.1")
        except Exception as ex:
            if task.done():
                _LOGGER.debug("Server is already shutdown")
                break
            retries - 1
            if retries <= 0:
                _LOGGER.exception("Failed to shutdown server")
            else:
                _LOGGER.warning(
                    "Failed to shutdown server (retries: %s)", retries, exc_info=ex
                )
            await asyncio.sleep(0.5)
        else:
            break


@server.command
async def run(*, immutable: bool = False, dry_run: OPTION_DRY_RUN = False) -> None:
    """
    Run ARK server.

    Args:
    ----
    dry_run: bool
        Do not actually start the server. Mostly for testing.

    immutable: bool
        Immutable/read only ARK server/steam install.

    """

    start_shutdown = asyncio.Event()
    loop = asyncio.get_event_loop()

    marker_file: Path | None = None
    task = asyncio.create_task(_run_server(dry_run=dry_run, immutable=immutable))
    cleanup_task = asyncio.create_task(_shutdown(start_shutdown, task))
    loop.add_signal_handler(signal.SIGINT, start_shutdown.set)
    loop.add_signal_handler(signal.SIGTERM, start_shutdown.set)

    try:
        marker_file = await asyncio.shield(task)
    except asyncio.CancelledError:
        start_shutdown.set()

    if not start_shutdown.is_set():
        start_shutdown.set()
    await cleanup_task
    if marker_file and await aos.path.exists(marker_file):
        await aos.remove(marker_file)
