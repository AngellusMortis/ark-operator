"""Conf handlers for kopf."""

import asyncio
import re
from http import HTTPStatus
from typing import Unpack

import kopf
from kubernetes_asyncio.client import ApiException

from ark_operator.data import ChangeEvent
from ark_operator.handlers.utils import DEFAULT_NAME, is_tracked, restart_with_lock
from ark_operator.k8s import get_cluster

NAME_PATTERN = re.compile(
    r"^(?P<instance_name>[^-]*)-(global-(ark-config|envs)|map-(envs|config)-(?P<map_id>[^-]*)|cluster-secrets)$"
)


@kopf.on.resume("configmap")  # type: ignore[arg-type]
@kopf.on.create("configmap")
@kopf.on.update("configmap")
@kopf.on.resume("secret")
@kopf.on.create("secret")
@kopf.on.update("secret")
async def on_update_conf(**kwargs: Unpack[ChangeEvent]) -> None:
    """Check ArkCluster configs for changes."""

    # do not run this handler first
    await asyncio.sleep(5)

    logger = kwargs["logger"]
    diff = kwargs["diff"]
    name = kwargs["name"]
    namespace = kwargs["namespace"] or DEFAULT_NAME
    if not diff or not name:
        logger.info("No change detected, skipping")
        return

    if not (match := NAME_PATTERN.match(name)):
        logger.info("Name %s does not match pattern", name)
        return

    instance_name = match.group("instance_name")
    map_id = match.group("map_id")
    if not is_tracked(instance_name, namespace):
        logger.info(
            "ArkCluster instance (%s, %s) is not tracked", instance_name, namespace
        )
        return

    try:
        cluster, status = await get_cluster(name=instance_name, namespace=namespace)
    except ApiException as ex:
        if ex.status == HTTPStatus.NOT_FOUND:
            logger.info(
                "ArkCluster instance (%s, %s) is not found", instance_name, namespace
            )
            return
        raise

    maps = [map_id] if map_id else cluster.server.all_maps
    logger.info("Restarting servers %s due to configuration update", maps)
    await restart_with_lock(
        name=instance_name,
        namespace=namespace,
        spec=cluster,
        reason="configuration update",
        active_volume=status.active_volume or "server-a",
        logger=logger,
    )
