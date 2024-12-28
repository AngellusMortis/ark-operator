"""ARK Operator."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import cast

from gamercon_async import GameRCON

from ark_operator.ark_utils import (
    copy_ark,
    has_newer_version,
    install_ark,
)
from ark_operator.data import ArkServerSpec, Config, Steam

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment]


async def install() -> None:
    """Install ARK."""

    config = Config(
        steam_install_dir=Path("/workspaces/ark-operator/steam/install"),
        ark_a_install_dir=Path("/workspaces/ark-operator/steam/ark_a"),
        ark_b_install_dir=Path("/workspaces/ark-operator/steam/ark_b"),
    )

    steam = Steam.create(install_dir=config.steam_install_dir)

    print("Install ARK A")
    print(
        f"ARK A has update: {await has_newer_version(steam, config.ark_a_install_dir)}"
    )
    await install_ark(steam, ark_dir=config.ark_a_install_dir)

    print("Copy ARK A -> B")
    await copy_ark(config.ark_a_install_dir, config.ark_b_install_dir)

    print("Install ARK B")
    print(
        f"ARK B has update: {await has_newer_version(steam, config.ark_b_install_dir)}"
    )
    await install_ark(steam, ark_dir=config.ark_b_install_dir)


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
            host=os.environ["RCON_IP"],
            port=s.rcon_port,
            password=os.environ["RCON_PASSWORD"],
        )
        for s in servers
    ]

    responses = await asyncio.gather(*tasks)
    for index, response in enumerate(responses):
        print(f"{servers[index].map_name} - {cmd}")
        print(response)


def start() -> None:
    """Run application."""

    if load_dotenv is not None:
        env_file = Path(".env")
        if env_file.exists():
            load_dotenv(dotenv_path=env_file)
        else:
            load_dotenv()

    spec = ArkServerSpec(
        maps=["official"],
        game_port_start=7780,
        rcon_port_start=27020,
    )
    asyncio.run(send_cmd_all(" ".join(sys.argv[1:]), spec=spec))


if __name__ == "__main__":
    start()
