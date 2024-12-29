import pytest

from ark_operator.decorators import async_only, sync_only
from ark_operator.exceptions import (
    AsynchronousOnlyOperationError,
    SynchronousOnlyOperationError,
)


@sync_only()
def _sync_only_func() -> None:
    pass


@async_only()
def _async_only_func() -> None:
    pass


def test_sync_only() -> None:
    """Test sync_only decorator in sync context."""

    _sync_only_func()


@pytest.mark.asyncio
async def test_sync_only_async() -> None:
    """Test sync_only decorator in async context."""

    with pytest.raises(SynchronousOnlyOperationError):
        _sync_only_func()


def test_async_only() -> None:
    """Test async_only decorator in sync context."""

    with pytest.raises(AsynchronousOnlyOperationError):
        _async_only_func()


@pytest.mark.asyncio
async def test_async_only_async() -> None:
    """Test async_only decorator in async context."""

    _async_only_func()
