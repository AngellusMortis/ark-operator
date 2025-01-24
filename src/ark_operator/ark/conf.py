"""ARK config parser."""

from __future__ import annotations

import logging
import secrets
import string
from base64 import b64decode, b64encode
from http import HTTPStatus
from typing import TYPE_CHECKING, cast, overload

import yaml
from aiofiles import open as aopen
from asyncache import cached
from cachetools import TTLCache
from kubernetes_asyncio.client import ApiException

from ark_operator.ark.utils import ENV, get_map_slug
from ark_operator.data import ArkClusterSecrets, ArkClusterSpec
from ark_operator.k8s import get_v1_client
from ark_operator.templates import loader
from ark_operator.utils import VERSION

if TYPE_CHECKING:
    from pathlib import Path

    import kopf
    from kubernetes_asyncio.client.models import V1ConfigMap

    from ark_operator.data import ArkClusterSpec


_LOGGER = logging.getLogger(__name__)
PASSWORD_CHARS = string.ascii_letters + string.digits
ERROR_NO_PASSWORD = "Could not get RCON password."  # noqa: S105


IniConf = dict[str, dict[str, str | list[str]]]


def read_config_from_lines(lines: list[str]) -> IniConf:
    """Read ARK config from string."""

    conf: IniConf = {}
    section = None
    for line in lines:
        line = line.strip()  # noqa: PLW2901
        if not line or line.startswith(";"):
            continue  # TODO: # pragma: no cover

        if line.startswith("[") and line.endswith("]"):
            section = line.lstrip("[").rstrip("]")
            conf[section] = {}
            continue

        try:
            key, value = line.split("=", 1)
        except Exception:  # TODO: # pragma: no cover
            _LOGGER.debug(line)
            raise

        value = value.strip()
        section = section or ""
        if section == "":
            _LOGGER.warning(  # TODO: # pragma: no cover
                "Found config setting without section %s", key
            )
        conf[section] = conf.get(section, {})
        key = key.strip()
        if key in conf[section]:  # TODO: # pragma: no cover
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
            for key, value in conf.pop("").items():  # TODO: # pragma: no cover
                await f.write(f"{key} = {value}\n")

        for section, values in conf.items():
            if first_section:
                first_section = False
            else:
                await f.write("\n")
            await f.write(f"[{section}]\n")

            for key, value in values.items():
                if isinstance(value, str):  # pragma: no branch
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


async def _read_secret(*, name: str, namespace: str) -> dict[str, str] | None:
    v1 = await get_v1_client()
    try:
        obj = await v1.read_namespaced_secret(name=name, namespace=namespace)
    except ApiException as ex:
        if ex.status == HTTPStatus.NOT_FOUND:
            return None
        raise  # TODO: # pragma: no cover

    data = cast(dict[str, str], obj.data)
    for key, value in data.items():
        data[key] = b64decode(value.encode("utf-8")).decode("utf-8")
    return data


async def read_secrets(*, name: str, namespace: str) -> dict[str, str] | None:
    """Read ARK cluster secrets."""

    return await _read_secret(name=f"{name}-cluster-secrets", namespace=namespace)


async def create_secrets(
    *, name: str, namespace: str, logger: kopf.Logger | None = None
) -> bool:
    """Create secrets for ARK Cluster."""

    logger = logger or _LOGGER
    secret_name = f"{name}-cluster-secrets"
    if await read_secrets(name=name, namespace=namespace):
        _LOGGER.warning("Secret %s already exists, skipping creation", secret_name)
        return False

    password = "".join(secrets.choice(PASSWORD_CHARS) for _ in range(32))
    secret_tmpl = loader.get_template("secret.yml.j2")
    _LOGGER.info("Create secret %s with new RCON password", secret_name)
    secret = yaml.safe_load(
        await secret_tmpl.render_async(
            instance_name=name,
            namespace=namespace,
            operator_version=VERSION,
            rcon_password=b64encode(password.encode("utf-8")).decode("utf-8"),
        )
    )
    v1 = await get_v1_client()
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
        await v1.delete_namespaced_secret(
            name=secret_name, namespace=namespace, propagation_policy="Foreground"
        )
    except Exception:  # noqa: BLE001  # TODO: # pragma: no cover
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
        raise  # TODO: # pragma: no cover

    return cast(dict[str, str], global_cm.data)


@cached(TTLCache(8, ENV.int("ARK_OP_TTL_CACHE", 30)))  # type: ignore[misc]
async def _get_global_config(name: str, namespace: str) -> dict[str, str]:
    return await _get_config_map(f"{name}-global-envs", namespace)


@cached(TTLCache(8, ENV.int("ARK_OP_TTL_CACHE", 30)))  # type: ignore[misc]
async def _get_global_ark_config(name: str, namespace: str) -> dict[str, str]:
    return await _get_config_map(f"{name}-global-ark-config", namespace)


async def _get_map_config(name: str, namespace: str, map_id: str) -> dict[str, str]:
    slug = get_map_slug(map_id)
    return await _get_config_map(f"{name}-map-envs-{slug}", namespace)


async def _get_map_ark_config(name: str, namespace: str, map_id: str) -> dict[str, str]:
    slug = get_map_slug(map_id)
    return await _get_config_map(f"{name}-map-ark-config-{slug}", namespace)


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


async def get_mods(
    *, name: str, namespace: str, spec: ArkClusterSpec
) -> dict[str, set[str]]:
    """Get list of mods with maps using them."""

    mods: dict[str, set[str]] = {}
    for map_id in spec.server.all_maps:
        envs = await get_map_envs(
            name=name, namespace=namespace, spec=spec, map_id=map_id
        )
        map_mods = list(envs.get("ARK_SERVER_MODS", "").split(","))
        if map_id == "BobsMissions_WP":
            map_mods.append("1005639")
        for mod_id in map_mods:
            maps = mods.get(mod_id, set())
            maps.add(map_id)
            mods[mod_id] = maps

    return mods


@cached(TTLCache(8, ENV.int("ARK_OP_TTL_CACHE", 60)))  # type: ignore[misc]
async def get_rcon_password(*, name: str, namespace: str) -> str:
    """Read RCON password for cluster."""

    secrets = await read_secrets(name=name, namespace=namespace)
    if not secrets or "ARK_SERVER_RCON_PASSWORD" not in secrets:
        raise RuntimeError(ERROR_NO_PASSWORD)

    return secrets["ARK_SERVER_RCON_PASSWORD"]


@cached(TTLCache(8, ENV.int("ARK_OP_TTL_CACHE", 300)))  # type: ignore[misc]
async def get_secrets(*, name: str, namespace: str) -> ArkClusterSecrets:
    """Read operator secrets for cluster."""

    secrets = await _read_secret(name=f"{name}-operator-secrets", namespace=namespace)
    if secrets:
        return ArkClusterSecrets(**secrets)
    return ArkClusterSecrets()
