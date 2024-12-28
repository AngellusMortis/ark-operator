"""ARK Operator templates."""

from jinja2 import Environment, PackageLoader, select_autoescape

loader = Environment(
    loader=PackageLoader("ark_operator"),
    autoescape=select_autoescape(),
    enable_async=True,
)
