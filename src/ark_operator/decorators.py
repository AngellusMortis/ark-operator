"""Helper decorators for TMS framework."""

from __future__ import annotations

from typing import TYPE_CHECKING, ParamSpec, TypeVar

from ark_operator.exceptions import (
    AsynchronousOnlyOperationError,
    SynchronousOnlyOperationError,
)
from ark_operator.utils import is_async

if TYPE_CHECKING:
    from collections.abc import Callable


P = ParamSpec("P")
R = TypeVar("R")


def sync_only() -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Ensure function is only called with no event loop."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if is_async():
                raise SynchronousOnlyOperationError

            return func(*args, **kwargs)

        return wrapper

    return decorator


def async_only() -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Ensure function is only called with no event loop."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if not is_async():
                raise AsynchronousOnlyOperationError

            return func(*args, **kwargs)

        return wrapper

    return decorator
