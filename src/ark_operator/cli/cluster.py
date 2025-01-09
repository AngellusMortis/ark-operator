"""ARK k8s Cluster CLI."""

from __future__ import annotations

from pathlib import Path  # required for cyclopts  # noqa: TC003
from typing import TYPE_CHECKING, Annotated, cast

from cyclopts import App, CycloptsError, Parameter

from ark_operator.ark import expand_maps
from ark_operator.cli.context import ClusterContext, get_all_context, set_context
from ark_operator.cli.options import (
    OPTION_ARK_SELECTOR,
    OPTION_ARK_SPEC,
    OPTION_DRY_RUN,
    OPTION_OPTIONAL_HOST,
    OPTION_RCON_PASSWORD,
)
from ark_operator.data import ArkClusterSpec
from ark_operator.k8s import are_crds_installed, close_k8s_client
from ark_operator.k8s import install_crds as install_crds_api
from ark_operator.k8s import uninstall_crds as uninstall_crds_api
from ark_operator.rcon import send_cmd_all
from ark_operator.steam import Steam
from ark_operator.utils import comma_list

if TYPE_CHECKING:
    from ipaddress import IPv4Address, IPv6Address


cluster = App(
    help="""
    ARK k8s Cluster CLI.

    Helpful commands for managing an ARK: Survival Ascended k8s server cluster.
"""
)

ERROR_HOST_REQUIRED = "Host is required from the option or from loadBalancerIP on spec."


def _get_context() -> ClusterContext:
    return cast(ClusterContext, get_all_context("cluster"))


def _require_host(spec: ArkClusterSpec | None) -> IPv4Address | IPv6Address:
    if not spec or not spec.server.load_balancer_ip:
        raise CycloptsError(msg=ERROR_HOST_REQUIRED)

    return spec.server.load_balancer_ip


@cluster.meta.default
def meta(
    *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
    spec: OPTION_ARK_SPEC,
    selector: OPTION_ARK_SELECTOR = ["@all"],  # noqa: B006\
    host: OPTION_OPTIONAL_HOST = None,
    rcon_password: OPTION_RCON_PASSWORD,
) -> int | None:
    """
    ARK k8s Cluster CLI.

    Helpful commands for managing an ARK: Survival Ascended k8s server cluster.
    """

    selector = comma_list(selector)
    selected_maps = expand_maps(selector.copy(), all_maps=spec.server.all_maps)
    set_context(
        "cluster",
        ClusterContext(
            spec=spec,
            selected_maps=selected_maps,
            host=host or _require_host(spec),
            rcon_password=rcon_password,
            parent=get_all_context("core"),  # type: ignore[arg-type]
        ),
    )
    return cluster(tokens)  # type: ignore[no-any-return]


@cluster.command
async def install_crds(*, force: bool = False) -> None:
    """Install ArkCluster CRDs."""

    try:
        await install_crds_api(force=force)
    finally:
        await close_k8s_client()


@cluster.command
async def uninstall_crds() -> None:
    """Uninstall ArkCluster CRDs."""

    try:
        await uninstall_crds_api()
    finally:
        await close_k8s_client()


@cluster.command
async def check_crds() -> int:
    """Check if CRDs are installed."""

    try:
        if not await are_crds_installed():
            return 1
    finally:
        await close_k8s_client()

    return 0


@cluster.command
async def init_volumes(base_dir: Path, *, dry_run: OPTION_DRY_RUN = False) -> None:
    """Initialize volumes for cluster."""

    context = _get_context()
    steam = Steam(base_dir / "server-a" / "steam")
    await steam.init_volumes(base_dir, spec=context.spec, dry_run=dry_run)


@cluster.command
async def rcon(*cmd: str) -> None:
    """Run rcon command for ARK server."""

    context = _get_context()
    await send_cmd_all(
        " ".join(cmd),
        host=context.host,
        password=context.rcon_password,
        spec=context.spec.server,
        servers=context.selected_maps,
    )


@cluster.command
async def save() -> None:
    """Run save rcon command for ARK server."""

    context = _get_context()
    await send_cmd_all(
        "SaveWorld",
        host=context.host,
        password=context.rcon_password,
        spec=context.spec.server,
        servers=context.selected_maps,
    )


@cluster.command
async def broadcast(*message: str) -> None:
    """Run send message via rcon to ARK server."""

    context = _get_context()
    await send_cmd_all(
        f"ServerChat {" ".join(message)}",
        host=context.host,
        password=context.rcon_password,
        spec=context.spec.server,
        servers=context.selected_maps,
    )


@cluster.command
async def shutdown() -> None:
    """Run shutdown server via rcon."""

    context = _get_context()
    await send_cmd_all(
        "SaveWorld",
        host=context.host,
        password=context.rcon_password,
        spec=context.spec.server,
        servers=context.selected_maps,
        close=False,
    )
    await send_cmd_all(
        "DoExit",
        host=context.host,
        password=context.rcon_password,
        spec=context.spec.server,
        servers=context.selected_maps,
    )
