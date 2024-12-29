"""ARK Operator rcon."""

import asyncio
import logging
import os
from typing import cast

from gamercon_async import GameRCON

from ark_operator.data import ArkServerSpec

_LOGGER = logging.getLogger(__name__)


async def send_cmd(cmd: str, *, host: str, port: int, password: str) -> str:
    """Run rcon command againt server."""

    async with GameRCON(host, port, password, timeout=5) as client:
        return cast(str, await client.send(cmd))


async def send_cmd_all(cmd: str, *, spec: ArkServerSpec) -> None:
    """Run rcon command against all servers."""

    servers = spec.all_servers
    tasks = [
        send_cmd(
            cmd,
            host=os.environ["ARK_SERVER_IP"],
            port=s.rcon_port,
            password=os.environ["ARK_SERVER_RCON_PASSWORD"],
        )
        for s in servers
    ]

    responses = await asyncio.gather(*tasks)
    for index, response in enumerate(responses):
        _LOGGER.info("%s - %s", servers[index].map_name, cmd)
        _LOGGER.info(response)
