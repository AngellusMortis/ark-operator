"""K8s utils functions."""

import re
from functools import lru_cache

POWER_RE = re.compile(r"^(?P<number>\d+)e(?P<power>\d+)$")
SUFFIX = "eptgmk"


@lru_cache(maxsize=100)
def convert_k8s_size(size: int | str) -> int:
    """Convert k8s resource size strings to ints."""

    if isinstance(size, int):
        return size

    size = size.lower()
    if match := POWER_RE.match(size):
        power = int(10 ** int(match.group("power")))
        return int(match.group("number")) * power

    divider = 1000
    if size.endswith("i"):
        divider = 1024
        size = size[:-1]

    if size[-1] not in SUFFIX:
        return int(size)

    suffix = size[-1]
    size = int(size[:-1])

    for index, compare in enumerate(SUFFIX):
        if compare == suffix:
            size = size * divider
            if suffix != "k":
                suffix = SUFFIX[index + 1]

    return size
