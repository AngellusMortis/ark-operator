"""Utils for running commands."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from asyncio.subprocess import PIPE
from collections.abc import Callable
from contextlib import suppress
from functools import partial
from shlex import split
from subprocess import CalledProcessError, CompletedProcess
from subprocess import run as subprocess_run
from typing import TYPE_CHECKING, Any, Literal, overload

from ark_operator.decorators import sync_only
from ark_operator.exceptions import CommandError
from ark_operator.log import LoggingLevel

if TYPE_CHECKING:
    from asyncio.streams import StreamReader

_LOGGER = logging.getLogger(__name__)
ERROR_PROCESSING = "Error processing output from command."

StreamCallback = Callable[[bytes], None]
UserCallback = Callable[
    [LoggingLevel | None, bytes, bool],
    tuple[LoggingLevel | None, bytes | None],
]
AnyReturn = CompletedProcess[str] | CompletedProcess[bytes] | CompletedProcess[None]


@overload
def run_sync(
    command: str,
    *,
    decode: Literal[True] = True,
    echo: bool = False,
    output_level: int | None = None,
    capture: Literal[True] = True,
    shell: bool = False,
    raw_output: bool = False,
    env: dict[str, str | None] | None = None,
    dry_run: Literal[False] = False,
    check: bool = False,
    callback: UserCallback | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> CompletedProcess[str]:  # pragma: no cover
    ...


@overload
def run_sync(
    command: str,
    *,
    decode: Literal[False],
    echo: bool = False,
    output_level: int | None = None,
    capture: Literal[True] = True,
    shell: bool = False,
    raw_output: bool = False,
    env: dict[str, str | None] | None = None,
    dry_run: Literal[False] = False,
    check: bool = False,
    callback: UserCallback | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> CompletedProcess[bytes]:  # pragma: no cover
    ...


@overload
def run_sync(
    command: str,
    *,
    decode: bool = True,
    echo: bool = False,
    output_level: int | None = None,
    capture: Literal[False],
    shell: bool = False,
    raw_output: bool = False,
    env: dict[str, str | None] | None = None,
    dry_run: bool = False,
    check: bool = False,
    callback: UserCallback | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> CompletedProcess[None]:  # pragma: no cover
    ...


@overload
def run_sync(
    command: str,
    *,
    decode: bool = True,
    echo: bool = False,
    output_level: int | None = None,
    capture: bool = True,
    shell: bool = False,
    raw_output: bool = False,
    env: dict[str, str | None] | None = None,
    dry_run: Literal[True],
    check: bool = False,
    callback: UserCallback | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> CompletedProcess[None]:  # pragma: no cover
    ...


@overload
def run_sync(
    command: str,
    *,
    decode: Literal[False],
    echo: bool = False,
    output_level: int | None = None,
    capture: bool = True,
    shell: bool = False,
    raw_output: bool = False,
    env: dict[str, str | None] | None = None,
    dry_run: bool = False,
    check: bool = False,
    callback: UserCallback | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> CompletedProcess[bytes] | CompletedProcess[None]:  # pragma: no cover
    ...


@overload
def run_sync(
    command: str,
    *,
    decode: Literal[True] = True,
    echo: bool = False,
    output_level: int | None = None,
    capture: bool = True,
    shell: bool = False,
    raw_output: bool = False,
    env: dict[str, str | None] | None = None,
    dry_run: bool = False,
    check: bool = False,
    callback: UserCallback | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> CompletedProcess[str] | CompletedProcess[None]:  # pragma: no cover
    ...


@overload
def run_sync(
    command: str,
    *,
    decode: bool = True,
    echo: bool = False,
    output_level: int | None = None,
    capture: bool = True,
    shell: bool = False,
    raw_output: bool = False,
    env: dict[str, str | None] | None = None,
    dry_run: bool = False,
    check: bool = False,
    callback: UserCallback | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> AnyReturn:  # pragma: no cover
    ...


@sync_only()
def run_sync(  # noqa: PLR0913
    command: str,
    *,
    decode: bool = True,
    echo: bool = False,
    output_level: int | None = None,
    capture: bool = True,
    shell: bool = False,
    raw_output: bool = False,
    env: dict[str, str | None] | None = None,
    dry_run: bool = False,
    check: bool = False,
    callback: UserCallback | None = None,
    **kwargs: Any,
) -> AnyReturn:
    """
    Run a command.

    Parameters
    ----------
    command: str
        The command to run
    decode: bool
        Automatically decode output to str
    echo: bool
        Log commands before running them
    output_level: int
        Output level of command running. Defaults to `logging.INFO` if
        `echo=True` else `logging.DEBUG`. Set to `logging.NOTSET` to disable.
    capture: bool
        capture the output from the command running
    shell: bool
        run the command using a shell (or exec if `False`)
    raw_output: bool
        write output raw to stdout/stderr instead of using logger
    env: dict[str, str | None]
        A mapping of environment variables to set for the child command, set env
        to `None` to delete it from the current env
    dry_run: bool
        Do not actually run the command
    check: bool
        Raise exception if command does not exit successfully
    callback: UserCallback
        Callback that is called for each processed line
    kwargs: Any
        Any extra args accepted by `asyncio.create_subprocess_shell`
        or `create_subprocess_exec`. `stdout` and `stderr` should _not_ be
        passed.

    `stdout` and `stderr` must _not_ be passed.

    **Must not** be ran inside of an `asyncio` loop as it creates its own. If you need
    async, use `run` instead.

    """

    loop = asyncio.new_event_loop()
    try:
        response = loop.run_until_complete(
            _run(
                command,
                decode=decode,
                echo=echo,
                output_level=output_level,
                capture=capture,
                shell=shell,  # nosec
                raw_output=raw_output,
                env=env,
                dry_run=dry_run,
                check=check,
                callback=callback,
                allow_sync=True,
                **kwargs,
            ),
        )
    finally:
        loop.close()
    return response


@overload
async def run_async(
    command: str,
    *,
    decode: Literal[True] = True,
    echo: bool = False,
    output_level: int | None = None,
    capture: Literal[True] = True,
    shell: bool = False,
    raw_output: bool = False,
    env: dict[str, str | None] | None = None,
    dry_run: Literal[False] = False,
    check: bool = False,
    callback: UserCallback | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> CompletedProcess[str]:  # pragma: no cover
    ...


@overload
async def run_async(
    command: str,
    *,
    decode: Literal[False],
    echo: bool = False,
    output_level: int | None = None,
    capture: Literal[True] = True,
    shell: bool = False,
    raw_output: bool = False,
    env: dict[str, str | None] | None = None,
    dry_run: Literal[False] = False,
    check: bool = False,
    callback: UserCallback | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> CompletedProcess[bytes]:  # pragma: no cover
    ...


@overload
async def run_async(
    command: str,
    *,
    decode: bool = True,
    echo: bool = False,
    output_level: int | None = None,
    capture: Literal[False],
    shell: bool = False,
    raw_output: bool = False,
    env: dict[str, str | None] | None = None,
    dry_run: bool = False,
    check: bool = False,
    callback: UserCallback | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> CompletedProcess[None]:  # pragma: no cover
    ...


@overload
async def run_async(
    command: str,
    *,
    decode: bool = True,
    echo: bool = False,
    output_level: int | None = None,
    capture: bool = True,
    shell: bool = False,
    raw_output: bool = False,
    env: dict[str, str | None] | None = None,
    dry_run: Literal[True],
    check: bool = False,
    callback: UserCallback | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> CompletedProcess[None]:  # pragma: no cover
    ...


@overload
async def run_async(
    command: str,
    *,
    decode: Literal[False],
    echo: bool = False,
    output_level: int | None = None,
    capture: bool = True,
    shell: bool = False,
    raw_output: bool = False,
    env: dict[str, str | None] | None = None,
    dry_run: bool = False,
    check: bool = False,
    callback: UserCallback | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> CompletedProcess[bytes] | CompletedProcess[None]:  # pragma: no cover
    ...


@overload
async def run_async(
    command: str,
    *,
    decode: Literal[True] = True,
    echo: bool = False,
    output_level: int | None = None,
    capture: bool = True,
    shell: bool = False,
    raw_output: bool = False,
    env: dict[str, str | None] | None = None,
    dry_run: bool = False,
    check: bool = False,
    callback: UserCallback | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> CompletedProcess[str] | CompletedProcess[None]:  # pragma: no cover
    ...


@overload
async def run_async(
    command: str,
    *,
    decode: bool = True,
    echo: bool = False,
    output_level: int | None = None,
    capture: bool = True,
    shell: bool = False,
    raw_output: bool = False,
    env: dict[str, str | None] | None = None,
    dry_run: bool = False,
    check: bool = False,
    callback: UserCallback | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> AnyReturn:  # pragma: no cover
    ...


async def run_async(  # noqa: PLR0913
    command: str,
    *,
    decode: bool = True,
    echo: bool = False,
    output_level: int | None = None,
    capture: bool = True,
    shell: bool = False,
    raw_output: bool = False,
    env: dict[str, str | None] | None = None,
    dry_run: bool = False,
    check: bool = False,
    callback: UserCallback | None = None,
    **kwargs: Any,
) -> AnyReturn:
    """
    Run a command async.

    Parameters
    ----------
    command: str
        The command to run
    decode: bool
        Automatically decode output to str
    echo: bool
        Log commands before running them
    output_level: int
        Output level of command running. Defaults to `logging.INFO` if
        `echo=True` else `logging.DEBUG`. Set to `logging.NOTSET` to disable.
    capture: bool
        capture the output from the command running
    shell: bool
        run the command using a shell (or exec if `False`)
    raw_output: bool
        write output raw to stdout/stderr instead of using logger
    env: dict[str, str | None]
        A mapping of environment variables to set for the child command, set env
        to `None` to delete it from the current env
    dry_run: bool
        Do not actually run the command
    check: bool
        Raise exception if command does not exit successfully
    callback: UserCallback
        Callback that is called for each processed line
    kwargs: Any
        Any extra args accepted by `asyncio.create_subprocess_shell`
        or `create_subprocess_exec`. `stdout` and `stderr` should _not_ be
        passed.

    `stdout` and `stderr` must _not_ be passed.

    """

    return await _run(
        command,
        decode=decode,
        echo=echo,
        output_level=output_level,
        capture=capture,
        shell=shell,  # nosec
        raw_output=raw_output,
        env=env,
        dry_run=dry_run,
        check=check,
        callback=callback,
        **kwargs,
    )


def _run_sync(
    command: str,
    *,
    shell: bool,
    decode: bool,
    check: bool,
    **kwargs: Any,  # noqa: ANN401
) -> CompletedProcess[None]:
    if shell:
        return subprocess_run(command, shell=True, **kwargs)  # noqa: PLW1510,S602

    args = split(command)
    return _decode_result(  # type: ignore[return-value]
        subprocess_run(args, shell=False, **kwargs),  # noqa: PLW1510,S603
        decode=decode,
        check=check,
    )


def _decode_result(result: AnyReturn, *, decode: bool, check: bool) -> AnyReturn:
    result.args = clean_command(result.args)

    if decode and isinstance(result.stderr, bytes):
        result = CompletedProcess(
            result.args,
            result.returncode,
            result.stdout.decode("utf-8"),
            result.stderr.decode("utf-8"),
        )

    if check and result.returncode != 0:
        raise CalledProcessError(
            result.returncode,
            result.args,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result


def _set_env(env: dict[str, str | None]) -> dict[str, str]:
    restore_env: dict[str, str] = {}

    for key, value in env.items():
        if key in os.environ:
            restore_env[key] = os.environ[key]
            if value is None:
                del os.environ[key]
        if value is not None:
            os.environ[key] = value

    return restore_env


def _restore_env(env: dict[str, str | None], restore_env: dict[str, str]) -> None:
    for key, value in env.items():
        if value is not None:
            os.environ.pop(key, None)
    for key, value in restore_env.items():
        os.environ[key] = value


def _write_output(line: bytes, *, is_stderr: bool, is_debug: bool) -> None:
    if is_debug:
        do_print = False
        if _LOGGER.isEnabledFor(logging.DEBUG):
            do_print = True
        if not do_print:
            return

    if is_stderr:
        sys.stderr.buffer.write(line)
        sys.stderr.buffer.flush()
    else:
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()


def _stream_callback(  # noqa: C901
    logger: logging.Logger,
    logger_args: dict[str, Any],
    user_callback: UserCallback | None,
    line: bytes | None,
) -> None:
    level: LoggingLevel | None = "INFO"
    args = {**logger_args}
    raw = bool(args.pop("raw", False))
    is_stderr = bool(args.get("stderr", False))
    match args.pop("level", None):
        case logging.DEBUG:
            level = "DEBUG"
        case logging.INFO:
            level = "INFO"
        case logging.WARNING:
            level = "WARNING"
        case logging.ERROR:
            level = "ERROR"
        case logging.NOTSET:
            level = None

    if args.pop("stderr", False):
        level = "ERROR"

    if user_callback is not None and line is not None:
        try:
            level, line = user_callback(level, line, is_stderr)
        except Exception as err:  # noqa: BLE001
            logger.warning("Error processing user callback: %s", repr(err))

    if level is not None and line is not None:
        if raw:
            _write_output(line, is_stderr=is_stderr, is_debug=level == "DEBUG")
        else:
            getattr(logger, level.lower())(
                line.decode("utf-8").rstrip("\n"),
                **args,
            )


_callback = partial(_stream_callback, _LOGGER)


async def _process_output(
    stream: StreamReader | None,
    *,
    callback: StreamCallback | None = None,
    capture: bool = True,
) -> bytes | None:
    """Read from stream line by line until EOF, display, and capture the lines."""

    output = []
    while stream:  # pragma: no branch
        line = await stream.readline()
        if not line:
            break

        if capture:
            output.append(line)
        if callback is not None:  # pragma: no branch
            callback(line)

    if capture:
        return b"".join(output)
    return None


async def _run_command(
    command: str,
    *,
    capture: bool = True,
    shell: bool = False,
    stdout_callback: StreamCallback | None = None,
    stderr_callback: StreamCallback | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> CompletedProcess[bytes] | CompletedProcess[None]:
    """Capture cmd's stdout/stderr and display them line by line."""

    # start process
    if shell:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=PIPE,
            stderr=PIPE,
            **kwargs,
        )
    else:
        process = await asyncio.create_subprocess_exec(
            *split(command),
            stdout=PIPE,
            stderr=PIPE,
            **kwargs,
        )

    # read child's stdout/stderr concurrently (capture and display)
    try:
        stdout, stderr = await asyncio.gather(
            _process_output(
                process.stdout,
                callback=stdout_callback,
                capture=capture,
            ),
            _process_output(
                process.stderr,
                callback=stderr_callback,
                capture=capture,
            ),
        )
    except Exception as ex:
        with suppress(Exception):
            process.kill()
        raise CommandError(ERROR_PROCESSING) from ex
    finally:
        # wait for the process to exit
        return_code = await process.wait()
    return CompletedProcess(command, return_code, stdout, stderr)


@overload
def clean_command(command: str) -> str:  # pragma: no cover
    ...


@overload
def clean_command(command: list[str]) -> list[str]:  # pragma: no cover
    ...


@overload
def clean_command(command: str | list[str]) -> str | list[str]:  # pragma: no cover
    ...


def clean_command(command: str | list[str]) -> str | list[str]:
    """Remove secrets from command to make it safe for printing."""

    if isinstance(command, str):
        command = re.sub(r"--token \w+", "--token ****", command)
        command = re.sub(r"ghp_\w+", "ghp_****", command)
    else:
        new_command = []
        for arg in command:
            arg = re.sub(r"--token \w+", "--token ****", arg)  # noqa: PLW2901
            arg = re.sub(r"ghp_\w+", "ghp_****", arg)  # noqa: PLW2901
            new_command.append(arg)
        command = new_command
    return command


def _echo_command(command: str, *, dry_run: bool, cwd: str | None = None) -> None:
    verb = "Run Command (dry)" if dry_run else "Run Command"
    cmd = clean_command(command)
    msg = f"{verb}: `{cmd}`"
    if cwd:
        msg = f"{verb} ({cwd}): `{cmd}`"
    _LOGGER.info(msg)


async def _run(  # noqa: PLR0913
    command: str,
    *,
    decode: bool = True,
    echo: bool = False,
    output_level: int | None = None,
    capture: bool = True,
    shell: bool = False,
    raw_output: bool = False,
    env: dict[str, str | None] | None = None,
    dry_run: bool = False,
    callback: UserCallback | None = None,
    check: bool = False,
    allow_sync: bool = False,
    **kwargs: Any,  # noqa: ANN401
) -> AnyReturn:
    if dry_run and not echo:
        echo = True

    if output_level is None:
        output_level = logging.INFO if echo else logging.DEBUG

    if "stderr" in kwargs or "stdout" in kwargs:
        msg = "stdout and stderr are not supported"
        raise ValueError(msg)

    env = env or {}
    restore_env = _set_env(env)

    if echo:
        _echo_command(command, dry_run=dry_run, cwd=kwargs.get("cwd"))
        if dry_run:
            return CompletedProcess(
                clean_command(command),
                0,
                None,
                None,
            )

    try:
        if raw_output and not capture and allow_sync:
            return _run_sync(
                command,
                shell=shell,
                decode=decode,
                check=check,
                **kwargs,
            )  # nosec

        logger_kwargs = {
            "level": output_level,
            "raw": raw_output,
        }
        # do not try to log binary data
        if not decode:
            logger_kwargs["level"] = logging.NOTSET
        stdout = partial(_callback, logger_kwargs, callback)
        stderr = partial(_callback, {**logger_kwargs, "stderr": True}, callback)
        return _decode_result(
            await _run_command(
                command,
                capture=capture,
                shell=shell,  # nosec
                stdout_callback=stdout,
                stderr_callback=stderr,
                **kwargs,
            ),
            decode=decode,
            check=check,
        )
    finally:
        _restore_env(env, restore_env)
