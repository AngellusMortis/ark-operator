"""ARK config parser."""

from __future__ import annotations

import logging
import secrets
import string
from http import HTTPStatus
from typing import TYPE_CHECKING, cast, overload

import yaml
from aiofiles import open as aopen
from asyncache import cached
from cachetools import TTLCache
from kubernetes_asyncio.client import ApiException

from ark_operator.ark.utils import ENV
from ark_operator.data import ArkClusterSpec
from ark_operator.k8s import get_v1_client
from ark_operator.templates import loader
from ark_operator.utils import VERSION

if TYPE_CHECKING:
    from pathlib import Path

    import kopf
    from kubernetes_asyncio.client.models import V1ConfigMap

    from ark_operator.data import ArkClusterSpec


_LOGGER = logging.getLogger(__name__)


async def read_config(path: Path) -> dict[str, dict[str, str]]:
    """Read ARK config file."""

    conf: dict[str, dict[str, str]] = {}
    async with aopen(path) as f:
        section = None
        for line in await f.readlines():
            line = line.strip()  # noqa: PLW2901
            if not line:
                continue

            if line.startswith("[") and line.endswith("]"):
                section = line.lstrip("[").rstrip("]")
                conf[section] = {}
                continue

            try:
                key, value = line.split("=", 1)
            except Exception:
                _LOGGER.debug(line)
                raise
            conf[section or ""][key.strip()] = value.strip()

    return conf


async def write_config(conf: dict[str, dict[str, str]], path: Path) -> None:
    """Write ARK config file."""

    async with aopen(path, "w") as f:
        first_section = True
        if "" in conf:
            for key, value in conf.pop("None").items():
                await f.write(f"{key} = {value}\n")

        for section, values in conf.items():
            if first_section:
                first_section = False
            else:
                await f.write("\n")
            await f.write(f"[{section}]\n")

            for key, value in values.items():
                await f.write(f"{key} = {value}\n")


@overload
def merge_conf(
    parent: dict[str, dict[str, str]],
    child: dict[str, dict[str, str]] | None,
    *,
    warn: bool = False,
) -> dict[str, dict[str, str]]: ...  # pragma: no cover


@overload
def merge_conf(
    parent: dict[str, dict[str, str]] | None,
    child: dict[str, dict[str, str]],
    *,
    warn: bool = False,
) -> dict[str, dict[str, str]]: ...  # pragma: no cover


@overload
def merge_conf(
    parent: None, child: None, *, warn: bool = False
) -> None: ...  # pragma: no cover


@overload
def merge_conf(
    parent: dict[str, dict[str, str]] | None,
    child: dict[str, dict[str, str]] | None,
    *,
    warn: bool = False,
) -> dict[str, dict[str, str]] | None: ...  # pragma: no cover


def merge_conf(
    parent: dict[str, dict[str, str]] | None,
    child: dict[str, dict[str, str]] | None,
    *,
    warn: bool = False,
) -> dict[str, dict[str, str]] | None:
    """Merge two ARK configs."""

    if parent is None and child is None:
        _LOGGER.debug("No configs to merge")
        return None

    if parent is None:
        _LOGGER.debug("No parent config to merge")
        return child

    if child is None:  # pragma: no cover
        _LOGGER.debug("No child config to merge")
        return parent

    for section, values in child.items():
        if section not in parent:
            parent[section] = {}

        for key, value in values.items():
            old_value = parent[section].get(key, value)
            if value != old_value:
                _log = _LOGGER.debug
                if warn:
                    _log = _LOGGER.warning
                _log(
                    "key %s: child value (%s) overwriting parent value (%s)",
                    key,
                    value,
                    old_value,
                )
            parent[section][key] = value

    return parent


async def create_secrets(
    *, name: str, namespace: str, logger: kopf.Logger | None = None
) -> bool:
    """Create secrets for ARK Cluster."""

    logger = logger or _LOGGER
    secret_name = f"{name}-cluster-secrets"
    v1 = await get_v1_client()
    try:
        await v1.read_namespaced_secret(name=secret_name, namespace=namespace)
    except ApiException as ex:
        if ex.status != HTTPStatus.NOT_FOUND:
            raise
    else:
        _LOGGER.warning("Secret %s already exists, skipping creation", secret_name)
        return False

    alphabet = string.ascii_letters + string.digits
    secret_tmpl = loader.get_template("secret.yml.j2")
    _LOGGER.info("Create secret %s with new RCON password", secret_name)
    secret = yaml.safe_load(
        await secret_tmpl.render_async(
            instance_name=name,
            namespace=namespace,
            operator_version=VERSION,
            rcon_password="".join(secrets.choice(alphabet) for _ in range(32)),
        )
    )
    await v1.create_namespaced_secret(namespace=namespace, body=secret)
    return True


async def delete_secrets(
    *, name: str, namespace: str, logger: kopf.Logger | None = None
) -> None:
    """Delete secrets for ARK cluster."""

    secret_name = f"{name}-cluster-secrets"
    logger = logger or _LOGGER
    logger.info("Deleting secrets %s", secret_name)
    v1 = await get_v1_client()
    try:
        await v1.delete_namespaced_secret(name=secret_name, namespace=namespace)
    except Exception:  # noqa: BLE001
        logger.warning("Failed to delete secret %s", secret_name)


async def _get_config_map(name: str, namespace: str) -> dict[str, str]:
    v1 = await get_v1_client()
    try:
        global_cm: V1ConfigMap = await v1.read_namespaced_config_map(
            name=name, namespace=namespace
        )
    except ApiException as ex:
        if ex.status == HTTPStatus.NOT_FOUND:
            return {}
        raise

    return cast(dict[str, str], global_cm.data)


@cached(TTLCache(8, ENV.int("ARK_OP_TTL_CACHE", 30)))  # type: ignore[misc]
async def _get_global_config(name: str, namespace: str) -> dict[str, str]:
    return await _get_config_map(f"{name}-global-envs", namespace)


async def _get_map_config(name: str, namespace: str, map_id: str) -> dict[str, str]:
    return await _get_config_map(f"{name}-map-envs-{map_id}", namespace)


async def get_map_envs(
    *, name: str, namespace: str, spec: ArkClusterSpec, map_id: str
) -> dict[str, str]:
    """Get envs for a given map."""

    envs = spec.global_settings.get_envs(map_id)
    global_envs = await _get_global_config(name, namespace)
    if map_id == "BobsMissions_WP":
        global_envs.pop("ARK_SERVER_PARAMS", None)
        global_envs.pop("ARK_SERVER_OPTS", None)
        global_envs.pop("ARK_SERVER_MODS", None)
    envs.update(**global_envs)
    envs.update(**await _get_map_config(name, namespace, map_id))

    return envs
