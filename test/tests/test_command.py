"""Test run util."""

from __future__ import annotations

import asyncio
import logging
import os
from subprocess import CalledProcessError
from unittest.mock import Mock, patch

import pytest

from ark_operator.command import run_async, run_sync
from ark_operator.exceptions import CommandError


def _assert_logs(
    caplog: pytest.LogCaptureFixture, logs: list[str], level: int = logging.INFO
) -> None:
    expected_records = {log: False for log in logs}
    for record in caplog.records:
        if record.message in expected_records:
            expected_records[record.message] = True
            assert record.levelno == level

    assert all(expected_records.values())


def _assert_not_logs(caplog: pytest.LogCaptureFixture, logs: list[str]) -> None:
    not_expected_records = {log: True for log in logs}
    for record in caplog.records:
        if record.message in not_expected_records:
            not_expected_records[record.message] = False

    assert all(not_expected_records.values())


def test_dry_run_sync(caplog: pytest.LogCaptureFixture) -> None:
    """Test dry_run on run util."""

    for i in range(2):
        if i == 0:
            result = run_sync("ls", dry_run=True)
        else:
            result = asyncio.run(run_async("ls", dry_run=True))

        assert result.args == "ls"
        assert result.returncode == 0
        assert result.stdout is None
        assert result.stderr is None

        assert "Run Command (dry): `ls`\n" in caplog.text


def test_no_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test shell on run util."""

    monkeypatch.delenv("FOO", raising=False)

    for i in range(2):
        if i == 0:
            result = run_sync("echo $FOO", env={"FOO": "BAR"}, shell=False)
        else:
            result = asyncio.run(
                run_async("echo $FOO", env={"FOO": "BAR"}, shell=False)
            )

        assert "FOO" not in os.environ

        assert result.args == "echo $FOO"
        assert result.returncode == 0
        assert result.stdout == "$FOO\n"
        assert not result.stderr


def test_env_add(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test env on run util."""

    monkeypatch.delenv("FOO", raising=False)

    for i in range(2):
        if i == 0:
            result = run_sync("echo $FOO", env={"FOO": "BAR"}, shell=True)
        else:
            result = asyncio.run(run_async("echo $FOO", env={"FOO": "BAR"}, shell=True))

        assert "FOO" not in os.environ

        assert result.args == "echo $FOO"
        assert result.returncode == 0
        assert result.stdout == "BAR\n"
        assert not result.stderr


def test_env_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test env on run util."""

    monkeypatch.setenv("FOO", "nope")
    for i in range(2):
        if i == 0:
            result = run_sync("echo $FOO", env={"FOO": "BAR"}, shell=True)
        else:
            result = asyncio.run(run_async("echo $FOO", env={"FOO": "BAR"}, shell=True))

        assert os.environ["FOO"] == "nope"

        assert result.args == "echo $FOO"
        assert result.returncode == 0
        assert result.stdout == "BAR\n"
        assert not result.stderr


def test_env_del(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test env on run util."""

    monkeypatch.setenv("FOO", "BAR")

    for i in range(2):
        if i == 0:
            result = run_sync("echo $FOO", env={"FOO": None}, shell=True)
        else:
            result = asyncio.run(run_async("echo $FOO", env={"FOO": None}, shell=True))

        assert "FOO" in os.environ

        assert result.args == "echo $FOO"
        assert result.returncode == 0
        assert result.stdout == "\n"
        assert not result.stderr


def test_no_capture() -> None:
    """Test capture on run util."""

    for i in range(2):
        if i == 0:
            result = run_sync("echo foo", capture=False)
        else:
            result = asyncio.run(run_async("echo foo", capture=False))

        assert result.args == "echo foo"
        assert result.returncode == 0
        assert result.stdout is None
        assert result.stderr is None


def test_output_debug(caplog: pytest.LogCaptureFixture) -> None:
    """Test output defaults to debug level on run util."""

    for i in range(2):
        result = run_sync("echo foo") if i == 0 else asyncio.run(run_async("echo foo"))

        assert result.args == "echo foo"
        assert result.returncode == 0
        assert result.stdout == "foo\n"
        assert not result.stderr

        assert "foo\n" in caplog.text
        for record in caplog.records:
            if record.msg == "foo\n":
                assert record.levelname == "DEBUG"


@pytest.mark.parametrize("level", [logging.WARNING, logging.ERROR])
def test_output_level(caplog: pytest.LogCaptureFixture, level: int) -> None:
    """Test output level for warning and error levels."""

    for i in range(2):
        if i == 0:
            result = run_sync("echo foo", output_level=level)
        else:
            result = asyncio.run(run_async("echo foo", output_level=level))

        assert result.args == "echo foo"
        assert result.returncode == 0
        assert result.stdout == "foo\n"
        assert not result.stderr

        _assert_logs(caplog, ["foo"], level)


def test_output_unexpected_level(caplog: pytest.LogCaptureFixture) -> None:
    """Test unexpected output level defaults to info."""

    for i in range(2):
        if i == 0:
            result = run_sync("echo foo", output_level=logging.FATAL)
        else:
            result = asyncio.run(run_async("echo foo", output_level=logging.FATAL))

        assert result.args == "echo foo"
        assert result.returncode == 0
        assert result.stdout == "foo\n"
        assert not result.stderr

        _assert_logs(caplog, ["foo"])


def test_output(caplog: pytest.LogCaptureFixture) -> None:
    """Test output on run util."""

    for i in range(2):
        if i == 0:
            result = run_sync("echo foo", output_level=logging.INFO)
        else:
            result = asyncio.run(run_async("echo foo", output_level=logging.INFO))

        assert result.args == "echo foo"
        assert result.returncode == 0
        assert result.stdout == "foo\n"
        assert not result.stderr

        _assert_logs(caplog, ["foo"])


def test_output_error(caplog: pytest.LogCaptureFixture) -> None:
    """Test output to stderr on run util."""

    for i in range(2):
        if i == 0:
            result = run_sync(">&2 echo foo", output_level=logging.INFO, shell=True)
        else:
            result = asyncio.run(
                run_async(">&2 echo foo", output_level=logging.INFO, shell=True),
            )

        assert result.args == ">&2 echo foo"
        assert result.returncode == 0
        assert not result.stdout
        assert result.stderr == "foo\n"

        _assert_logs(caplog, ["foo"], logging.ERROR)


def test_echo(caplog: pytest.LogCaptureFixture) -> None:
    """Test echo on run util."""

    for i in range(2):
        if i == 0:
            result = run_sync("echo foo", echo=True)
        else:
            result = asyncio.run(run_async("echo foo", echo=True))

        assert result.args == "echo foo"
        assert result.returncode == 0
        assert result.stdout == "foo\n"
        assert not result.stderr

        _assert_logs(caplog, ["Run Command: `echo foo`", "foo"])


def test_echo_cwd(caplog: pytest.LogCaptureFixture) -> None:
    """Test echo with a different current working dir on run util."""

    for i in range(2):
        if i == 0:
            result = run_sync("echo foo", echo=True, cwd="/")
        else:
            result = asyncio.run(run_async("echo foo", echo=True, cwd="/"))

        assert result.args == "echo foo"
        assert result.returncode == 0
        assert result.stdout == "foo\n"
        assert not result.stderr

        _assert_logs(caplog, ["Run Command (/): `echo foo`", "foo"])


def test_no_decode() -> None:
    """Test decode run util."""

    for i in range(2):
        if i == 0:
            result = run_sync("echo foo", decode=False)
        else:
            result = asyncio.run(run_async("echo foo", decode=False))

        assert result.args == "echo foo"
        assert result.returncode == 0
        assert result.stdout == b"foo\n"
        assert result.stderr == b""


@patch("ark_operator.command._process_output")
def test_error(mock_process: Mock) -> None:
    """Test exceptions are still raised."""

    mock_process.side_effect = RuntimeError("test")

    for i in range(2):
        with pytest.raises(CommandError):  # noqa: PT012
            if i == 0:
                run_sync("echo foo")
            else:
                asyncio.run(run_async("echo foo"))


def test_check() -> None:
    """Test check argument are still raised."""

    for i in range(2):
        with pytest.raises(CalledProcessError):  # noqa: PT012
            if i == 0:
                run_sync("false", check=True)
            else:
                asyncio.run(run_async("false", check=True))


def test_no_strip(caplog: pytest.LogCaptureFixture) -> None:
    """Test characters not stripped from output."""

    for i in range(2):
        if i == 0:
            result = run_sync(
                'echo "     foo  "', output_level=logging.INFO, shell=True
            )
        else:
            result = asyncio.run(
                run_async('echo "     foo  "', output_level=logging.INFO, shell=True),
            )

        assert result.args == 'echo "     foo  "'
        assert result.returncode == 0
        assert result.stdout == "     foo  \n"
        assert not result.stderr

        _assert_logs(caplog, ["     foo  "])


def test_no_stdout() -> None:
    """Test stdout and stderr do not work."""

    for i in range(2):
        with pytest.raises(  # noqa: PT012
            ValueError,
            match="stdout and stderr are not supported",
        ):
            if i == 0:
                run_sync("echo foo", stdout=None)
            else:
                asyncio.run(run_async("echo foo", stdout=None))


def test_no_stderr() -> None:
    """Test stdout and stderr do not work."""

    for i in range(2):
        with pytest.raises(  # noqa: PT012
            ValueError,
            match="stdout and stderr are not supported",
        ):
            if i == 0:
                run_sync("echo foo", stderr=None)
            else:
                asyncio.run(run_async("echo foo", stderr=None))


def test_callback(caplog: pytest.LogCaptureFixture) -> None:
    """Test callback."""

    def _callback(level: str, line: bytes, is_stderr: bool) -> tuple[str, bytes]:  # noqa: ARG001
        return level, line

    for i in range(2):
        callback = Mock(side_effect=_callback)
        if i == 0:
            result = run_sync("echo foo", callback=callback, output_level=logging.INFO)
        else:
            asyncio.run(
                run_async("echo foo", callback=callback, output_level=logging.INFO),
            )

        assert result.args == "echo foo"
        assert result.returncode == 0
        assert result.stdout == "foo\n"
        assert not result.stderr

        _assert_logs(caplog, ["foo"])
        callback.assert_called_once_with("INFO", b"foo\n", False)


def test_callback_stderr(caplog: pytest.LogCaptureFixture) -> None:
    """Test callback passes is_stderr correctly."""

    def _callback(level: str, line: bytes, is_stderr: bool) -> tuple[str, bytes]:  # noqa: ARG001
        return level, line

    for i in range(2):
        callback = Mock(side_effect=_callback)
        if i == 0:
            result = run_sync(
                ">&2 echo foo",
                callback=callback,
                shell=True,
                output_level=logging.INFO,
            )
        else:
            asyncio.run(
                run_async(
                    ">&2 echo foo",
                    callback=callback,
                    shell=True,
                    output_level=logging.INFO,
                ),
            )

        assert result.args == ">&2 echo foo"
        assert result.returncode == 0
        assert not result.stdout
        assert result.stderr == "foo\n"

        _assert_logs(caplog, ["foo"], logging.ERROR)
        callback.assert_called_once_with("ERROR", b"foo\n", True)


def test_callback_level() -> None:
    """Test callback allows changing output level."""

    def _callback(level: str, line: bytes, is_stderr: bool) -> tuple[str, bytes]:  # noqa: ARG001
        return "debug", line

    for i in range(2):
        callback = Mock(side_effect=_callback)
        if i == 0:
            result = run_sync("echo foo", callback=callback, output_level=logging.INFO)
        else:
            asyncio.run(
                run_async("echo foo", callback=callback, output_level=logging.INFO),
            )

        assert result.args == "echo foo"
        assert result.returncode == 0
        assert result.stdout == "foo\n"
        assert not result.stderr

        callback.assert_called_once_with("INFO", b"foo\n", False)


def test_callback_suppress() -> None:
    """Test callback allows supressing logging."""

    def _callback(
        level: str,
        line: bytes,  # noqa: ARG001
        is_stderr: bool,  # noqa: ARG001
    ) -> tuple[str, bytes | None]:
        return level, None

    for i in range(2):
        callback = Mock(side_effect=_callback)
        if i == 0:
            result = run_sync("echo foo", callback=callback, output_level=logging.INFO)
        else:
            asyncio.run(
                run_async("echo foo", callback=callback, output_level=logging.INFO),
            )

        assert result.args == "echo foo"
        assert result.returncode == 0
        assert result.stdout == "foo\n"
        assert not result.stderr

        callback.assert_called_once_with("INFO", b"foo\n", False)


def test_callback_error(caplog: pytest.LogCaptureFixture) -> None:
    """Test callback catches and logs user errors."""

    for i in range(2):
        callback = Mock(side_effect=Exception("test"))
        if i == 0:
            result = run_sync("echo foo", callback=callback)
        else:
            asyncio.run(run_async("echo foo", callback=callback))

        assert result.args == "echo foo"
        assert result.returncode == 0
        assert result.stdout == "foo\n"
        assert not result.stderr

        _assert_logs(
            caplog,
            ["Error processing user callback: Exception('test')"],
            logging.WARNING,
        )
        callback.assert_called_once_with("DEBUG", b"foo\n", False)


def test_raw(caplog: pytest.LogCaptureFixture) -> None:
    """Test raw_output on run util."""

    for i in range(2):
        if i == 0:
            result = run_sync("echo foo", raw_output=True, output_level=logging.INFO)
        else:
            asyncio.run(
                run_async("echo foo", raw_output=True, output_level=logging.INFO),
            )

        assert result.args == "echo foo"
        assert result.returncode == 0
        assert result.stdout == "foo\n"
        assert not result.stderr

        _assert_not_logs(caplog, ["foo"])


def test_raw_stderr(caplog: pytest.LogCaptureFixture) -> None:
    """Test raw_output on run util for stderr."""

    for i in range(2):
        if i == 0:
            result = run_sync(
                ">&2 echo foo",
                raw_output=True,
                output_level=logging.INFO,
                shell=True,
            )
        else:
            asyncio.run(
                run_async(
                    ">&2 echo foo",
                    raw_output=True,
                    output_level=logging.INFO,
                    shell=True,
                ),
            )

        assert result.args == ">&2 echo foo"
        assert result.returncode == 0
        assert not result.stdout
        assert result.stderr == "foo\n"

        _assert_not_logs(caplog, ["foo"])


def test_raw_debug_disabled(caplog: pytest.LogCaptureFixture) -> None:
    """Test raw_output on run util for debug level."""

    caplog.set_level(logging.INFO)
    for i in range(2):
        if i == 0:
            result = run_sync("echo foo", raw_output=True, output_level=logging.DEBUG)
        else:
            asyncio.run(
                run_async("echo foo", raw_output=True, output_level=logging.DEBUG),
            )

        assert result.args == "echo foo"
        assert result.returncode == 0
        assert result.stdout == "foo\n"
        assert not result.stderr

        _assert_not_logs(caplog, ["foo"])


def test_raw_debug(caplog: pytest.LogCaptureFixture) -> None:
    """Test raw_output on run util for debug level."""

    caplog.set_level(logging.DEBUG)
    for i in range(2):
        if i == 0:
            result = run_sync("echo foo", raw_output=True, output_level=logging.DEBUG)
        else:
            asyncio.run(
                run_async("echo foo", raw_output=True, output_level=logging.DEBUG),
            )

        assert result.args == "echo foo"
        assert result.returncode == 0
        assert result.stdout == "foo\n"
        assert not result.stderr

        _assert_not_logs(caplog, ["foo"])


def test_sync() -> None:
    """Test sync (raw_output=True, capture=False on run) on run util."""

    result = run_sync(
        "echo foo", raw_output=True, capture=False, output_level=logging.INFO
    )

    assert result.args == ["echo", "foo"]
    assert result.returncode == 0
    assert result.stdout is None
    assert result.stderr is None


def test_sync_shell() -> None:
    """Test sync (raw_output=True, capture=False on run) on run util with shell."""

    result = run_sync(
        "echo foo",
        shell=True,
        raw_output=True,
        capture=False,
        output_level=logging.INFO,
    )

    assert result.args == "echo foo"
    assert result.returncode == 0
    assert result.stdout is None
    assert result.stderr is None
