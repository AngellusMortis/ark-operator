"""ARK service utils."""

from __future__ import annotations

import json
import logging
from http import HTTPStatus
from typing import TYPE_CHECKING, cast

import kopf
import yaml
from kubernetes_asyncio.client import ApiException

from ark_operator.ark.utils import get_map_slug
from ark_operator.k8s import get_v1_client
from ark_operator.templates import loader
from ark_operator.utils import VERSION

if TYPE_CHECKING:
    from kubernetes_asyncio.client import V1Service

    from ark_operator.data import ArkClusterSpec

_LOGGER = logging.getLogger(__name__)
ERROR_SVC = "Error creating service"


async def get_service(
    *, name: str, namespace: str, game: bool = True
) -> V1Service | None:
    """Get service for ARK cluster."""

    svc_name = f"{name}" if game else f"{name}-rcon"
    v1 = await get_v1_client()
    try:
        obj = await v1.read_namespaced_service(namespace=namespace, name=svc_name)
    except ApiException as ex:
        if ex.status == HTTPStatus.NOT_FOUND:
            return None
        raise  # TODO: # pragma: no cover

    return obj


async def _create_service(
    *,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
    logger: kopf.Logger | None = None,
    game: bool = True,
) -> bool:
    logger = logger or _LOGGER
    exists = await get_service(name=name, namespace=namespace, game=game)

    v1 = await get_v1_client()

    servers = spec.server.all_servers.values()
    if game:
        ports = [(f"ark-{get_map_slug(s.map_id)}", s.port) for s in servers]
    else:
        ports = [(f"rcon-{get_map_slug(s.map_id)}", s.rcon_port) for s in servers]

    template_name = "service-game.yml.j2" if game else "service-rcon.yml.j2"
    svc_name = f"{name}" if game else f"{name}-rcon"
    svc_tmpl = loader.get_template(template_name)
    svc = yaml.safe_load(
        await svc_tmpl.render_async(
            instance_name=name,
            annotations=json.dumps(spec.service.annotations)
            if spec.service.annotations
            else None,
            operator_version=VERSION,
            load_balancer_ip=spec.service.load_balancer_ip,
            ports=ports,
        )
    )

    try:
        if exists:
            obj = await v1.patch_namespaced_service(
                name=svc_name,
                namespace=namespace,
                body=svc,
            )
        else:
            obj = await v1.create_namespaced_service(
                namespace=namespace,
                body=svc,
            )
    except Exception as ex:  # TODO: # pragma: no cover
        raise kopf.TemporaryError(ERROR_SVC, delay=5) from ex

    logger.info("%s service: %s", "Patched" if exists else "Created", obj.metadata.name)
    return True


async def create_services(
    *,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
    logger: kopf.Logger | None = None,
) -> bool:
    """Create services for ARK cluster."""

    return any(
        [
            await _create_service(
                name=name,
                namespace=namespace,
                spec=spec,
                logger=logger,
                game=True,
            ),
            await _create_service(
                name=name,
                namespace=namespace,
                spec=spec,
                logger=logger,
                game=False,
            ),
        ]
    )


async def delete_services(
    *, name: str, namespace: str, logger: kopf.Logger | None = None
) -> None:
    """Delete services for ARK cluster."""

    svc_names = [f"{name}", f"{name}-rcon"]
    logger = logger or _LOGGER
    logger.info("Deleting services %s", svc_names)
    v1 = await get_v1_client()

    for svc_name in svc_names:
        try:
            await v1.delete_namespaced_service(
                name=svc_name, namespace=namespace, propagation_policy="Foreground"
            )
        except Exception:  # noqa: BLE001  # TODO: # pragma: no cover
            logger.warning("Failed to delete service %s", svc_name)


async def get_cluster_host(
    *,
    name: str,
    namespace: str,
    spec: ArkClusterSpec,
) -> str | None:
    """Get host for ArkCluster."""

    if spec.service.load_balancer_ip:
        return str(spec.service.load_balancer_ip)

    svc = await get_service(name=name, namespace=namespace, game=False)
    if svc:
        return cast(str | None, svc.spec.load_balancer_ip or svc.spec.cluster_ip)

    return None
