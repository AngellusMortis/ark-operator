"""ARK Operator logging."""

import logging
import logging.config
import sys
from typing import Any, Literal

from pythonjsonlogger import json
from rich.console import Console
from rich.logging import RichHandler

LoggingFormat = Literal["rich", "json", "auto"]
LoggingLevel = Literal[
    "CRITICAL", "FATAL", "ERROR", "WARN", "WARNING", "INFO", "DEBUG", "NOTSET"
]
JSON_FIELDS = [
    "message",
    "levelname",
    "name",
    "asctime",
    "threadName",
    "module",
    "funcName",
    "levelno",
    "pathname",
    "lineno",
    "filename",
]
DEFAULT_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "loggers": {
        "asyncio": {
            "level": "WARNING",
        },
        "urllib3": {
            "level": "WARNING",
        },
        # steam loggers
        "CDNClient": {
            "level": "WARNING",
        },
        "CMServerList": {
            "level": "WARNING",
        },
        "SteamClient": {
            "level": "WARNING",
        },
        "Connection": {
            "level": "WARNING",
        },
    },
}


def init_logging(
    logging_format: LoggingFormat | None = None,
    level: LoggingLevel = "NOTSET",
    config: dict[str, Any] | None = None,
) -> None:
    """
    Initialize logging.

    If not provided, will default to rich if on a TTY, otherwise, JSON. Value of `None`
    will skip logging setup.
    """

    console: Console | None = Console(width=200)
    if logging_format == "auto":
        # pretty logger when running with a TTY, JSON logger otherwise
        logging_format = "rich" if (sys.stdin and sys.stdin.isatty()) else "json"
        # if logging is set to auto, let the width of the console be set dynamically
        console = None

    match logging_format:
        case "rich":
            logging.basicConfig(
                level=level,
                format="%(message)s",
                datefmt="[%X]",
                handlers=[RichHandler(console=console)],
            )
        case "json":
            handler = logging.StreamHandler()
            format_str = "".join([f"%({m})" for m in JSON_FIELDS])
            formatter = json.JsonFormatter(format_str)
            handler.setFormatter(formatter)

            logging.basicConfig(
                level=level,
                format="%(message)s",
                handlers=[handler],
            )

    if config:
        logging.config.dictConfig(config)
