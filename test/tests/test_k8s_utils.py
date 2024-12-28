"""Test k8s utils."""

import pytest

from ark_operator.k8s_utils import convert_k8s_size


@pytest.mark.parametrize(
    ("value", "output"),
    [
        ("100", 100),
        (100, 100),
        ("12e2", 12 * pow(10, 2)),
        ("10E", 10 * 1000 * 1000 * 1000 * 1000 * 1000 * 1000),
        ("63P", 63 * 1000 * 1000 * 1000 * 1000 * 1000),
        ("82T", 82 * 1000 * 1000 * 1000 * 1000),
        ("18G", 18 * 1000 * 1000 * 1000),
        ("452M", 452 * 1000 * 1000),
        ("1000K", 1000 * 1000),
        ("74Ei", 74 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024),
        ("10Pi", 10 * 1024 * 1024 * 1024 * 1024 * 1024),
        ("111Ti", 111 * 1024 * 1024 * 1024 * 1024),
        ("2468Gi", 2468 * 1024 * 1024 * 1024),
        ("3Mi", 3 * 1024 * 1024),
        ("1Ki", 1024),
    ],
)
def test_convert_k8s_size(value: int | str, output: int) -> None:
    """Test convert_k8s_size."""

    assert convert_k8s_size(value) == output
