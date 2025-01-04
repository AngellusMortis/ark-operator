"""ARK Operator."""

from __future__ import annotations

import sys
from pathlib import Path

from ark_operator.cli import app

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment]


def _main() -> int:
    """Run application."""

    if load_dotenv is not None:
        env_file = Path(".env")
        if env_file.exists():
            load_dotenv(dotenv_path=env_file)
        else:
            load_dotenv()

    return_code = app.meta()
    if return_code is None:
        return_code = 0
    return return_code  # type: ignore[no-any-return]


if __name__ == "__main__":
    sys.exit(_main())
