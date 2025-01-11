"""Test ARK Operator RCON."""

from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from ark_operator.data import ArkServerSpec
from ark_operator.exceptions import RCONError
from ark_operator.rcon import send_cmd, send_cmd_all
from gamercon_async.gamercon_async import TimeoutError as RCONTimeoutError

SPEC = ArkServerSpec(
    maps=["BobsMissions_WP", "TheIsland_WP"],
)
PYTEST_BUG = "pytest bug not able to detect exception when ran with other tests"


@patch("ark_operator.rcon.GameRCON")
@pytest.mark.asyncio
async def test_send_cmd(mock_rcon: Mock) -> None:
    """Test send_cmd."""

    mock_client = Mock()
    mock_client.__aenter__ = AsyncMock()
    mock_client.send = AsyncMock()
    mock_client.__aexit__ = AsyncMock()
    mock_rcon.return_value = mock_client

    await send_cmd("testCMD", host="test", port=123, password="password")

    mock_rcon.assert_called_once_with("test", 123, "password", timeout=3)
    mock_client.__aenter__.assert_awaited_once()
    mock_client.send.assert_awaited_once_with("testCMD")
    mock_client.__aexit__.assert_awaited_once()


@patch("ark_operator.rcon.GameRCON")
@pytest.mark.asyncio
async def test_send_cmd_client_reused(mock_rcon: Mock) -> None:
    """Test send_cmd."""

    mock_client = Mock()
    mock_client.__aenter__ = AsyncMock()
    mock_client.send = AsyncMock()
    mock_client.__aexit__ = AsyncMock()
    mock_rcon.return_value = mock_client

    await send_cmd("testCMD", host="test", port=123, password="password", close=False)
    await send_cmd("testCMD2", host="test", port=123, password="password")

    mock_rcon.assert_called_once_with("test", 123, "password", timeout=3)
    mock_client.__aenter__.assert_awaited_once()
    mock_client.send.assert_has_awaits([call("testCMD"), call("testCMD2")])
    mock_client.__aexit__.assert_awaited_once()


@patch("ark_operator.rcon.GameRCON")
@pytest.mark.asyncio
async def test_send_cmd_no_close(mock_rcon: Mock) -> None:
    """Test send_cmd."""

    mock_client = Mock()
    mock_client.__aenter__ = AsyncMock()
    mock_client.send = AsyncMock()
    mock_client.__aexit__ = AsyncMock()
    mock_rcon.return_value = mock_client

    await send_cmd("testCMD", host="test", port=123, password="password", close=False)

    mock_rcon.assert_called_once_with("test", 123, "password", timeout=3)
    mock_client.__aenter__.assert_awaited_once()
    mock_client.send.assert_awaited_once_with("testCMD")
    mock_client.__aexit__.assert_not_awaited()


@patch("ark_operator.rcon.GameRCON")
@pytest.mark.xfail(reason=PYTEST_BUG)
@pytest.mark.asyncio
async def test_send_cmd_error(mock_rcon: Mock) -> None:
    """Test send_cmd."""

    mock_client = Mock()
    mock_client.__aenter__ = AsyncMock()
    mock_client.send = AsyncMock(side_effect=Exception("test"))
    mock_client.__aexit__ = AsyncMock()
    mock_rcon.return_value = mock_client

    with pytest.raises(RCONError):
        await send_cmd("testCMD", host="test", port=123, password="password")

    mock_rcon.assert_called_once_with("test", 123, "password", timeout=3)
    mock_client.__aenter__.assert_awaited_once()
    mock_client.send.assert_awaited_once_with("testCMD")
    mock_client.__aexit__.assert_awaited_once()


@patch("ark_operator.rcon.GameRCON")
@pytest.mark.asyncio
async def test_send_cmd_all(mock_rcon: Mock) -> None:
    """Test send_cmd_all."""

    mock_client = Mock()
    mock_client.__aenter__ = AsyncMock()
    mock_client.send = AsyncMock()
    mock_client.__aexit__ = AsyncMock()
    mock_rcon.return_value = mock_client

    await send_cmd_all(
        "testCMD", spec=SPEC.model_copy(deep=True), host="test", password="password"
    )

    assert call("test", 27020, "password", timeout=3) in mock_rcon.call_args_list
    assert call("test", 27021, "password", timeout=3) in mock_rcon.call_args_list
    assert mock_client.__aenter__.await_count == 2
    mock_client.send.assert_has_awaits(
        [
            call("testCMD"),
            call("testCMD"),
        ]
    )
    assert mock_client.__aexit__.await_count == 2


@patch("ark_operator.rcon.GameRCON")
@pytest.mark.asyncio
async def test_send_cmd_all_no_close(mock_rcon: Mock) -> None:
    """Test send_cmd_all."""

    mock_client = Mock()
    mock_client.__aenter__ = AsyncMock()
    mock_client.send = AsyncMock()
    mock_client.__aexit__ = AsyncMock()
    mock_rcon.return_value = mock_client

    await send_cmd_all(
        "testCMD",
        spec=SPEC.model_copy(deep=True),
        host="test",
        password="password",
        close=False,
    )

    assert call("test", 27020, "password", timeout=3) in mock_rcon.call_args_list
    assert call("test", 27021, "password", timeout=3) in mock_rcon.call_args_list
    assert mock_client.__aenter__.await_count == 2
    mock_client.send.assert_has_awaits(
        [
            call("testCMD"),
            call("testCMD"),
        ]
    )
    mock_client.__aexit__.assert_not_awaited()


@patch("ark_operator.rcon.GameRCON")
@pytest.mark.xfail(reason=PYTEST_BUG)
@pytest.mark.asyncio
async def test_send_cmd_all_exception(mock_rcon: Mock) -> None:
    """Test send_cmd_all."""

    mock_client = Mock()
    mock_client.__aenter__ = AsyncMock()
    mock_client.send = AsyncMock(side_effect=Exception("test"))
    mock_client.__aexit__ = AsyncMock()
    mock_rcon.return_value = mock_client

    with pytest.raises(RCONError):
        await send_cmd_all(
            "testCMD", spec=SPEC.model_copy(deep=True), host="test", password="password"
        )

    assert call("test", 27020, "password", timeout=3) in mock_rcon.call_args_list
    assert call("test", 27021, "password", timeout=3) in mock_rcon.call_args_list
    assert mock_client.__aenter__.await_count == 2
    assert mock_client.__aexit__.await_count == 2


@patch("ark_operator.rcon.GameRCON")
@pytest.mark.xfail(reason=PYTEST_BUG)
@pytest.mark.asyncio
async def test_send_cmd_all_exception_timeout(mock_rcon: Mock) -> None:
    """Test send_cmd_all."""

    mock_client = Mock()
    mock_client.__aenter__ = AsyncMock()
    mock_client.send = AsyncMock(side_effect=RCONTimeoutError("test"))
    mock_client.__aexit__ = AsyncMock()
    mock_rcon.return_value = mock_client

    with pytest.raises(RCONError):
        await send_cmd_all(
            "testCMD", spec=SPEC.model_copy(deep=True), host="test", password="password"
        )

    assert call("test", 27020, "password", timeout=3) in mock_rcon.call_args_list
    assert call("test", 27021, "password", timeout=3) in mock_rcon.call_args_list
    assert mock_client.__aenter__.await_count == 2
    assert mock_client.__aexit__.await_count == 2

@patch("ark_operator.rcon.GameRCON")
@pytest.mark.asyncio
async def test_send_cmd_all_exception_return(mock_rcon: Mock) -> None:
    """Test send_cmd_all."""

    mock_client = Mock()
    mock_client.__aenter__ = AsyncMock()
    mock_client.send = AsyncMock(side_effect=[Exception("test"), "test"])
    mock_client.__aexit__ = AsyncMock()
    mock_rcon.return_value = mock_client

    responses = await send_cmd_all(
        "testCMD",
        spec=SPEC.model_copy(deep=True),
        host="test",
        password="password",
        raise_exceptions=False,
    )

    assert call("test", 27020, "password", timeout=3) in mock_rcon.call_args_list
    assert call("test", 27021, "password", timeout=3) in mock_rcon.call_args_list
    assert mock_client.__aenter__.await_count == 2
    mock_client.send.assert_has_awaits(
        [
            call("testCMD"),
            call("testCMD"),
        ]
    )
    assert mock_client.__aexit__.await_count == 2
    assert isinstance(responses["BobsMissions_WP"], RCONError)
    assert responses["TheIsland_WP"] == "test"
