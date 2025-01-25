"""Conf handlers for kopf."""

import asyncio
import re
from http import HTTPStatus
from typing import Unpack

import kopf
from kubernetes_asyncio.client import ApiException

from ark_operator.ark import get_active_volume, get_map_id_from_slug
from ark_operator.data import ChangeEvent
from ark_operator.handlers.utils import (
    DEFAULT_NAME,
    DRY_RUN,
    is_tracked,
    restart_with_lock,
)
from ark_operator.k8s import get_cluster

NAME_PATTERN = re.compile(
    r"^(?P<instance_name>[^-]*)-(global-(ark-config|envs)|map-(ark-config|envs)-(?P<map_slug>.*)|cluster-secrets)$"
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
    map_slug = match.group("map_slug")
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

    if (
        not status.initalized
        or not status.ready
        or not status.state
        or not status.state.startswith("Running")
    ):
        logger.info(
            "ArkCluster instance (%s, %s) is not running, skipping restart",
            instance_name,
            namespace,
        )
        return

    maps = (
        [get_map_id_from_slug(map_slug, tuple(cluster.server.all_maps))]
        if map_slug
        else cluster.server.all_maps
    )
    logger.info("Restarting servers %s due to configuration update", maps)
    active_volume = status.active_volume or await get_active_volume(
        name=name, namespace=namespace, spec=cluster
    )
    await restart_with_lock(
        name=instance_name,
        namespace=namespace,
        spec=cluster,
        reason="configuration update",
        active_volume=active_volume,
        active_buildid=status.active_buildid,
        servers=maps,
        logger=logger,
        dry_run=DRY_RUN,
        trigger_time=kwargs["started"],
    )
