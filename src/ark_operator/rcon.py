"""ARK Operator rcon."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import TYPE_CHECKING, cast

from gamercon_async import GameRCON

from ark_operator.exceptions import RCONError

if TYPE_CHECKING:
    from ipaddress import IPv4Address, IPv6Address

    from kopf import Logger

    from ark_operator.data import ArkServerSpec

_LOGGER = logging.getLogger(__name__)
_CONNECTIONS: dict[str, GameRCON] = {}
ERROR_RCON = "Exception running RCON command"


async def get_client(
    *, host: str | IPv4Address | IPv6Address, port: int, password: str
) -> GameRCON:
    """Get connection for RCON server."""

    name = f"{host!s}:{port}"
    client = _CONNECTIONS.get(name)
    if client is None:
        client = GameRCON(str(host), port, password, timeout=3)
        await client.__aenter__()
        _CONNECTIONS[name] = client

    return client


async def close_client(*, host: str | IPv4Address | IPv6Address, port: int) -> None:
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
    cmd: str,
    *,
    host: str | IPv4Address | IPv6Address,
    port: int,
    password: str,
    close: bool = True,
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

    return cast(str, response)


async def send_cmd_all(  # noqa: PLR0913
    cmd: str,
    *,
    host: str | IPv4Address | IPv6Address,
    password: str,
    spec: ArkServerSpec,
    close: bool = True,
    raise_exceptions: bool = True,
    servers: list[str] | None = None,
    logger: logging.Logger | Logger | None = None,
) -> dict[str, str | BaseException]:
    """Run rcon command against all servers."""

    from ark_operator.ark import expand_maps

    logger = logger or _LOGGER
    servers = servers or ["@all"]
    objs = [
        spec.all_servers[s] for s in expand_maps(servers, all_maps=spec.active_maps)
    ]
    tasks = [
        send_cmd(
            cmd,
            host=host,
            port=s.rcon_port,
            password=password,
            close=False,
        )
        for s in objs
    ]

    try:
        responses = await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        if close:
            await close_clients()

    return_responses: dict[str, str | BaseException] = {}
    for index, response in enumerate(responses):
        return_responses[objs[index].map_id] = response
        if isinstance(response, Exception):
            if "timeout" in repr(response.__context__).lower():
                logger.info("%s - %s", objs[index].map_name, cmd)
                logger.warning("Timeout")
                continue

            if raise_exceptions:
                raise response

            logger.exception(
                "Error while sending command %s to server %s",
                cmd,
                objs[index].map_name,
                exc_info=response,
            )
            continue

        logger.info("%s - %s", objs[index].map_name, cmd)
        logger.info(str(response).strip())

    return return_responses
