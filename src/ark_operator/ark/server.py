"""ARK operator code for PVCs."""

from __future__ import annotations

import json
import logging
from http import HTTPStatus
from typing import TYPE_CHECKING

import kopf
import yaml
from kubernetes_asyncio.client import ApiException

from ark_operator.ark.conf import get_map_envs
from ark_operator.ark.utils import ARK_SERVER_IMAGE_VERSION, get_map_name, get_map_slug
from ark_operator.k8s import get_v1_client
from ark_operator.templates import loader
from ark_operator.utils import VERSION

if TYPE_CHECKING:
    from kubernetes_asyncio.client import V1Pod

    from ark_operator.data import ArkClusterSpec

ERROR_POD = "Error creating server pod for map {map_id}"
_LOGGER = logging.getLogger(__name__)


async def get_server_pod(*, name: str, namespace: str, map_id: str) -> V1Pod | None:
    """Get server pod."""

    map_slug = get_map_slug(map_id)
    pod_name = f"{name}-{map_slug}"

    v1 = await get_v1_client()
    try:
        obj = await v1.read_namespaced_pod(namespace=namespace, name=pod_name)
    except ApiException as ex:
        if ex.status == HTTPStatus.NOT_FOUND:
            return None
        raise

    return obj


async def create_server_pod(  # noqa: PLR0913
    *,
    name: str,
    namespace: str,
    map_id: str,
    active_volume: str,
    spec: ArkClusterSpec,
    logger: kopf.Logger | None = None,
    dry_run: bool = False,
    force_create: bool = False,
) -> bool:
    """Create ARK server job."""

    logger = logger or _LOGGER
    exists = (
        await get_server_pod(name=name, namespace=namespace, map_id=map_id) is not None
    )

    if exists and not force_create:
        return False

    v1 = await get_v1_client()
    map_name = get_map_name(map_id)
    map_slug = get_map_slug(map_id)
    pod_name = f"{name}-{map_slug}"
    envs = await get_map_envs(name=name, namespace=namespace, spec=spec, map_id=map_id)
    has_global_gus = "ARK_SERVER_GLOBAL_GUS" in envs
    has_global_game = "ARK_SERVER_GLOBAL_GAME" in envs
    has_map_gus = "ARK_SERVER_MAP_GUS" in envs
    has_map_game = "ARK_SERVER_MAP_GAME" in envs

    pod_tmpl = loader.get_template("server-pod.yml.j2")
    pod = yaml.safe_load(
        await pod_tmpl.render_async(
            instance_name=name,
            namespace=namespace,
            uid=spec.run_as_user,
            gid=spec.run_as_group,
            node_selector=json.dumps(spec.node_selector)
            if spec.node_selector
            else None,
            tolerations=json.dumps(spec.tolerations) if spec.tolerations else None,
            resources=json.dumps(spec.server.resources)
            if spec.server.resources
            else None,
            spec=spec.model_dump_json(),
            dry_run=dry_run,
            image_version=ARK_SERVER_IMAGE_VERSION,
            operator_version=VERSION,
            map_id=map_id,
            map_name=map_name,
            map_slug=map_slug,
            active_volume=active_volume,
            envs=envs,
            has_global_gus=has_global_gus,
            has_global_game=has_global_game,
            has_map_gus=has_map_gus,
            has_map_game=has_map_game,
            game_port=envs["ARK_SERVER_GAME_PORT"],
            rcon_port=envs["ARK_SERVER_RCON_PORT"],
        )
    )

    try:
        if exists:
            obj = await v1.patch_namespaced_pod(
                name=pod_name,
                namespace=namespace,
                body=pod,
            )
        else:
            obj = await v1.create_namespaced_pod(
                namespace=namespace,
                body=pod,
            )
    except Exception as ex:
        raise kopf.PermanentError(ERROR_POD.format(map_id=map_id)) from ex

    logger.info(
        "%s server pod: %s", "Patched" if exists else "Created", obj.metadata.name
    )
    return True


async def delete_server_pod(
    *, name: str, namespace: str, map_id: str, logger: kopf.Logger | None = None
) -> None:
    """Delete secrets for ARK cluster."""

    map_slug = get_map_slug(map_id)
    pod_name = f"{name}-{map_slug}"
    logger = logger or _LOGGER
    logger.info("Deleting server pod %s", pod_name)
    v1 = await get_v1_client()
    try:
        await v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
    except Exception:  # noqa: BLE001
        logger.warning("Failed to delete server pod %s", pod_name)
