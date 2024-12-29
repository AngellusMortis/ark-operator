"""ARK Operator."""

from __future__ import annotations

from pathlib import Path

from ark_operator.cli import app

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment]


def _main() -> None:
    """Run application."""

    if load_dotenv is not None:
        env_file = Path(".env")
        if env_file.exists():
            load_dotenv(dotenv_path=env_file)
        else:
            load_dotenv()

    app.meta()


if __name__ == "__main__":
    _main()
