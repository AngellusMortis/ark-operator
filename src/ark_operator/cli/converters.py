"""CLI converters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ark_operator.utils import convert_timedelta

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import timedelta

    from cyclopts import Token

ERROR_INVALID_TD = "Invalid timedelta value"


def timedelta_converter(type_: type, tokens: Sequence[Token]) -> timedelta:  # noqa: ARG001
    """Convert timedelta."""

    value = convert_timedelta(tokens[0].value)
    if isinstance(value, str):
        raise ValueError(ERROR_INVALID_TD)  # noqa: TRY004

    return value
