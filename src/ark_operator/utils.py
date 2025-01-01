"""ARK utils."""

import asyncio


def is_async() -> bool:
    """Test if inside asyncio thread."""

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        return loop.is_running()
    return False
