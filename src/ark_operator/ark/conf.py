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


IniConf = dict[str, dict[str, str | list[str]]]


def read_config_from_lines(lines: list[str]) -> IniConf:
    """Read ARK config from string."""

    conf: IniConf = {}
    section = None
    for line in lines:
        line = line.strip()  # noqa: PLW2901
        if not line or line.startswith(";"):
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

        value = value.strip()
        section = section or ""
        if section == "":
            _LOGGER.warning("Found config setting without section %s", key)
        conf[section] = conf.get(section, {})
        key = key.strip()
        if key in conf[section]:
            existing_value = conf[section][key]
            if isinstance(existing_value, str):
                existing_value = [existing_value]
            existing_value.append(value)
            conf[section][key] = existing_value
        else:
            conf[section][key] = value

    return conf


async def read_config(path: Path) -> IniConf:
    """Read ARK config file."""

    async with aopen(path) as f:
        return read_config_from_lines(await f.readlines())


async def write_config(conf: IniConf, path: Path) -> None:
    """Write ARK config file."""

    async with aopen(path, "w") as f:
        first_section = True
        if "" in conf:
            for key, value in conf.pop("").items():
                await f.write(f"{key} = {value}\n")

        for section, values in conf.items():
            if first_section:
                first_section = False
            else:
                await f.write("\n")
            await f.write(f"[{section}]\n")

            for key, value in values.items():
                if isinstance(value, str):
                    value = [value]  # noqa: PLW2901
                for item in value:
                    await f.write(f"{key} = {item}\n")


@overload
def merge_conf(
    parent: IniConf,
    child: IniConf | None,
    *,
    warn: bool = False,
) -> IniConf: ...  # pragma: no cover


@overload
def merge_conf(
    parent: IniConf | None,
    child: IniConf,
    *,
    warn: bool = False,
) -> IniConf: ...  # pragma: no cover


@overload
def merge_conf(
    parent: None, child: None, *, warn: bool = False
) -> None: ...  # pragma: no cover


@overload
def merge_conf(
    parent: IniConf | None,
    child: IniConf | None,
    *,
    warn: bool = False,
) -> IniConf | None: ...  # pragma: no cover


def merge_conf(
    parent: IniConf | None,
    child: IniConf | None,
    *,
    warn: bool = False,
) -> IniConf | None:
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


@cached(TTLCache(8, ENV.int("ARK_OP_TTL_CACHE", 30)))  # type: ignore[misc]
async def _get_global_ark_config(name: str, namespace: str) -> dict[str, str]:
    return await _get_config_map(f"{name}-global-ark-config", namespace)


async def _get_map_config(name: str, namespace: str, map_id: str) -> dict[str, str]:
    return await _get_config_map(f"{name}-map-envs-{map_id}", namespace)


async def _get_map_ark_config(name: str, namespace: str, map_id: str) -> dict[str, str]:
    return await _get_config_map(f"{name}-map-ark-config-{map_id}", namespace)


async def get_map_envs(
    *, name: str, namespace: str, spec: ArkClusterSpec, map_id: str
) -> dict[str, str]:
    """Get envs for a given map."""

    envs = spec.global_settings.get_envs(map_id)
    server = spec.server.all_servers[map_id]
    envs["ARK_SERVER_GAME_PORT"] = str(server.port)
    envs["ARK_SERVER_RCON_PORT"] = str(server.rcon_port)

    global_envs = await _get_global_config(name, namespace)
    if map_id == "BobsMissions_WP":
        global_envs.pop("ARK_SERVER_PARAMS", None)
        global_envs.pop("ARK_SERVER_OPTS", None)
        global_envs.pop("ARK_SERVER_MODS", None)
    envs.update(**global_envs)
    envs.update(**await _get_map_config(name, namespace, map_id))

    global_ark_config = await _get_global_ark_config(name, namespace)
    if map_id != "BobsMissions_WP":
        if "GameUserSettings.ini" in global_ark_config:
            envs["ARK_SERVER_GLOBAL_GUS"] = "/srv/ark/conf/global/GameUserSettings.ini"
        if "Game.ini" in global_ark_config:
            envs["ARK_SERVER_GLOBAL_GAME"] = "/srv/ark/conf/global/Game.ini"

    map_ark_config = await _get_map_ark_config(name, namespace, map_id)
    if "GameUserSettings.ini" in map_ark_config:
        envs["ARK_SERVER_MAP_GUS"] = "/srv/ark/conf/map/GameUserSettings.ini"
    if "Game.ini" in map_ark_config:
        envs["ARK_SERVER_MAP_GAME"] = "/srv/ark/conf/map/Game.ini"

    return envs
