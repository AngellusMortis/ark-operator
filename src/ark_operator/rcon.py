"""ARK Operator rcon."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import TYPE_CHECKING, cast

from gamercon_async import GameRCON

from ark_operator.exceptions import RCONError

if TYPE_CHECKING:
    from ark_operator.data import ArkServerSpec

_LOGGER = logging.getLogger(__name__)
_CONNECTIONS: dict[str, GameRCON] = {}
ERROR_RCON = "Exception running RCON command"


async def get_client(*, host: str, port: int, password: str) -> GameRCON:
    """Get connection for RCON server."""

    name = f"{host}:{port}"
    client = _CONNECTIONS.get(name)
    if client is None:
        client = GameRCON(host, port, password, timeout=3)
        await client.__aenter__()
        _CONNECTIONS[name] = client

    return client


async def close_client(*, host: str, port: int) -> None:
    """Close open client."""

    client = _CONNECTIONS.pop(f"{host}:{port}", None)
    if client:  # pragma: no branch
        with suppress(Exception):
            await client.__aexit__(None, None, None)


async def close_clients() -> None:
    """Close all open clients."""

    for name, client in list(_CONNECTIONS.items()):
        with suppress(Exception):
            await client.__aexit__(None, None, None)
        del _CONNECTIONS[name]


async def send_cmd(
    cmd: str, *, host: str, port: int, password: str, close: bool = True
) -> str:
    """Run rcon command againt server."""

    try:
        client = await get_client(host=host, port=port, password=password)
        response = await client.send(cmd)
    except Exception as ex:
        raise RCONError(ERROR_RCON) from ex
    finally:
        if close:
            await close_client(host=host, port=port)

    return cast(str, response[0])


async def send_cmd_all(  # noqa: PLR0913
    cmd: str,
    *,
    host: str,
    password: str,
    spec: ArkServerSpec,
    close: bool = True,
    raise_exceptions: bool = True,
) -> dict[str, str | BaseException]:
    """Run rcon command against all servers."""

    servers = spec.all_servers
    tasks = [
        send_cmd(
            cmd,
            host=host,
            port=s.rcon_port,
            password=password,
            close=False,
        )
        for s in servers
    ]

    try:
        responses = await asyncio.gather(*tasks, return_exceptions=not raise_exceptions)
    finally:
        if close:
            await close_clients()

    return_responses: dict[str, str | BaseException] = {}
    for index, response in enumerate(responses):
        return_responses[servers[index].map_id] = response
        if isinstance(response, Exception):
            _LOGGER.exception(
                "Error while sending command %s to server %s",
                cmd,
                servers[index].map_name,
                exc_info=response,
            )
            continue

        _LOGGER.info("%s - %s", servers[index].map_name, cmd)
        _LOGGER.info(response)

    return return_responses
