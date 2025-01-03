"""ARK Operator CLI."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, cast

from cyclopts import App, CycloptsError, Parameter

from ark_operator.ark import expand_maps
from ark_operator.cli.context import ClusterContext, get_all_context, set_context
from ark_operator.cli.options import (
    OPTION_ARK_SELECTOR,
    OPTION_ARK_SPEC,
    OPTION_OPTIONAL_IP,
    OPTION_RCON_PASSWORD,
)
from ark_operator.rcon import send_cmd_all

if TYPE_CHECKING:
    from ipaddress import IPv4Address, IPv6Address

    from ark_operator.data import ArkClusterSpec


cluster = App(
    help="""
    ARK Cluster CLI.

    Helpful commands for managing an ARK: Survival Ascended k8s server cluster.
"""
)

_LOGGER = logging.getLogger(__name__)
ERROR_IP_REQUIRED = "IP is required from the option or from loadBalancerIP on spec."


def _get_context() -> ClusterContext:
    return cast(ClusterContext, get_all_context("cluster"))


@cluster.meta.default
def meta(
    *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
    spec: OPTION_ARK_SPEC,
    selector: OPTION_ARK_SELECTOR = ["@all"],  # noqa: B006
    ip: OPTION_OPTIONAL_IP = None,
    rcon_password: OPTION_RCON_PASSWORD,
) -> None:
    """ARK Operator."""

    maps = expand_maps(selector.copy(), all_maps=spec.server.all_maps)
    print(maps, spec.server.all_maps)
    set_context(
        "cluster",
        ClusterContext(
            spec=spec,
            map_selector=maps,
            ip=ip or _require_ip(spec),
            rcon_password=rcon_password,
            parent=get_all_context("core"),  # type: ignore[arg-type]
        ),
    )
    cluster(tokens)


def _require_ip(spec: ArkClusterSpec) -> IPv4Address | IPv6Address:
    if not spec.server.load_balancer_ip:
        raise CycloptsError(msg=ERROR_IP_REQUIRED)

    return spec.server.load_balancer_ip


@cluster.command
async def rcon(*cmd: str) -> None:
    """Run rcon command for ARK server."""

    context = _get_context()
    await send_cmd_all(
        " ".join(cmd),
        host=context.ip,
        password=context.rcon_password,
        spec=context.spec.server,
        servers=context.map_selector,
    )


@cluster.command
async def save() -> None:
    """Run save rcon command for ARK server."""

    context = _get_context()
    await send_cmd_all(
        "SaveWorld",
        host=context.ip,
        password=context.rcon_password,
        spec=context.spec.server,
        servers=context.map_selector,
    )


@cluster.command
async def broadcast(*message: str) -> None:
    """Run send message via rcon to ARK server."""

    context = _get_context()
    await send_cmd_all(
        f"ServerChat {" ".join(message)}",
        host=context.ip,
        password=context.rcon_password,
        spec=context.spec.server,
        servers=context.map_selector,
    )


@cluster.command
async def shutdown() -> None:
    """Run shutdown server via rcon."""

    context = _get_context()
    await send_cmd_all(
        "SaveWorld",
        host=context.ip,
        password=context.rcon_password,
        spec=context.spec.server,
        servers=context.map_selector,
        close=False,
    )
    await send_cmd_all(
        "DoExit",
        host=context.ip,
        password=context.rcon_password,
        spec=context.spec.server,
        servers=context.map_selector,
    )
