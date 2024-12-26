"""ARK Operator."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from rcon.source import Client

from ark_operator.ark_utils import copy_ark, has_newer_version, install_ark
from ark_operator.data import Config, Steam

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment]


def install() -> None:
    """Install ARK."""

    config = Config(
        steam_install_dir=Path("/workspaces/ark-operator/steam/install"),
        ark_a_install_dir=Path("/workspaces/ark-operator/steam/ark_a"),
        ark_b_install_dir=Path("/workspaces/ark-operator/steam/ark_b"),
    )

    steam = Steam.create(install_dir=config.steam_install_dir)

    print("Install ARK A")
    print(f"ARK A has update: {has_newer_version(steam, config.ark_a_install_dir)}")
    install_ark(steam, ark_dir=config.ark_a_install_dir)

    print("Copy ARK A -> B")
    copy_ark(config.ark_a_install_dir, config.ark_b_install_dir)

    print("Install ARK B")
    print(f"ARK B has update: {has_newer_version(steam, config.ark_b_install_dir)}")
    install_ark(steam, ark_dir=config.ark_b_install_dir)


def rcon(cmd: str, *args: str) -> None:
    """Run rcon command against all servers."""

    servers = [
        (27020, "Club Ark"),
        (27021, "The Island"),
        (27022, "The Center"),
        (27023, "Scorched Earth"),
        (27024, "Aberration"),
        (27025, "Extinction"),
    ]

    for port, name in servers:
        with Client(
            os.environ["RCON_IP"], port, passwd=os.environ["RCON_PASSWORD"]
        ) as client:
            print(f"{name} - {cmd} {' '.join(args)}")
            response = client.run(cmd, *args)
        print(response)


def start() -> None:
    """Run application."""

    if load_dotenv is not None:
        env_file = Path(".env")
        if env_file.exists():
            load_dotenv(dotenv_path=env_file)
        else:
            load_dotenv()

    rcon(sys.argv[1], *sys.argv[2:])


if __name__ == "__main__":
    start()
