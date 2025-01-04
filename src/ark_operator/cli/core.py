"""ARK Operator CLI."""

from __future__ import annotations

from typing import Annotated, cast

from cyclopts import App, Parameter

from ark_operator.cli.cluster import cluster
from ark_operator.cli.context import CoreContext, get_all_context, set_context
from ark_operator.cli.options import (
    OPTION_LOG_CONFIG,
    OPTION_LOG_FORMAT,
    OPTION_LOG_LEVEL,
)
from ark_operator.cli.server import server
from ark_operator.log import DEFAULT_LOG_CONFIG, init_logging

app = App(
    help="""
    ARK Operator CLI.

    Helpful commands for managing an ARK: Survival Ascended cluster in k8s and
    interacting with the k8s operator.
"""
)
app.command(server.meta, name="server")
app.command(cluster.meta, name="cluster")


def _get_context() -> CoreContext:
    return cast(CoreContext, get_all_context("core"))


@app.meta.default
def meta(
    *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
    logging_format: OPTION_LOG_FORMAT = "auto",
    logging_level: OPTION_LOG_LEVEL = "NOTSET",
    logging_config: OPTION_LOG_CONFIG = DEFAULT_LOG_CONFIG,
) -> int | None:
    """ARK Operator."""

    set_context(
        "core", CoreContext(logging_format=logging_format, logging_level=logging_level)
    )
    init_logging(logging_format, logging_level, config=logging_config)

    return app(tokens)  # type: ignore[no-any-return]
