"""Test ARK Operator log stuff."""

from __future__ import annotations

import sys
from unittest.mock import Mock, patch

import pytest
from pythonjsonlogger import json
from rich.logging import RichHandler

from ark_operator.log import LoggingFormat, init_logging


@pytest.mark.parametrize("log_format", ["auto", "rich"])
@patch("ark_operator.log.logging")
def test_init_logging_rich(
    mock_logging: Mock, log_format: LoggingFormat | None
) -> None:
    """Test init_logging with Rich handler"""

    with patch.object(sys, "stdin") as mock_stdin:
        mock_stdin.isatty = Mock(return_value=log_format == "auto")
        init_logging(logging_format=log_format)

    mock_logging.basicConfig.assert_called_once()
    assert "handlers" in mock_logging.basicConfig.call_args_list[0].kwargs

    handlers = mock_logging.basicConfig.call_args_list[0].kwargs["handlers"]
    assert len(handlers) == 1
    assert isinstance(handlers[0], RichHandler) is True


@pytest.mark.parametrize("log_format", ["auto", "json"])
@patch("ark_operator.log.logging")
def test_init_logging_json(
    mock_logging: Mock, log_format: LoggingFormat | None
) -> None:
    """Test init_logging with JSON format handler"""

    mock_handler = Mock()
    mock_logging.StreamHandler = Mock(return_value=mock_handler)

    with patch.object(sys, "stdin") as mock_stdin:
        mock_stdin.isatty = Mock(return_value=log_format != "auto")
        init_logging(logging_format=log_format)

    mock_logging.basicConfig.assert_called_once()
    assert "handlers" in mock_logging.basicConfig.call_args_list[0].kwargs

    handlers = mock_logging.basicConfig.call_args_list[0].kwargs["handlers"]
    assert len(handlers) == 1
    assert handlers[0] == mock_handler

    mock_handler.setFormatter.assert_called_once()

    args = mock_handler.setFormatter.call_args_list[0].args
    assert len(args) == 1
    assert isinstance(args[0], json.JsonFormatter) is True


@patch("ark_operator.log.logging")
def test_init_logging_basic(mock_logging: Mock) -> None:
    """Test init_logging with basic format handler"""

    mock_handler = Mock()
    mock_logging.StreamHandler = Mock(return_value=mock_handler)

    init_logging(logging_format="basic")

    mock_logging.basicConfig.assert_called_once()
    assert "handlers" in mock_logging.basicConfig.call_args_list[0].kwargs

    handlers = mock_logging.basicConfig.call_args_list[0].kwargs["handlers"]
    assert len(handlers) == 1
    assert handlers[0] == mock_handler

    mock_handler.setFormatter.assert_not_called()


@patch("ark_operator.log.logging")
def test_init_logging_none(mock_logging: Mock) -> None:
    """Test init_logging with logging disabled"""

    with patch.object(sys, "stdin") as mock_stdin:
        mock_stdin.isatty = Mock(return_value=True)
        init_logging(logging_format=None)

    mock_logging.basicConfig.assert_not_called()


@patch("ark_operator.log.logging")
def test_init_logging_config(mock_logging: Mock) -> None:
    """Test init_logging with logging disabled"""

    with patch.object(sys, "stdin") as mock_stdin:
        mock_stdin.isatty = Mock(return_value=True)
        init_logging(logging_format=None, config={"test": "test"})

    mock_logging.basicConfig.assert_not_called()
    mock_logging.config.dictConfig.assert_called_once_with({"test": "test"})
