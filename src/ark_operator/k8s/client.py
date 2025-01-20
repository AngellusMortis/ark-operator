"""K8s resource client."""

import logging

from kubernetes_asyncio import client, config
from kubernetes_asyncio.client.api_client import ApiClient

_CLIENT: ApiClient | None = None
_LOGGER = logging.getLogger(__name__)


async def close_k8s_client() -> None:
    """Clean up k8s client."""

    global _CLIENT  # noqa: PLW0603

    if _CLIENT is None:
        return

    await _CLIENT.close()
    _CLIENT = None


async def get_k8s_client() -> ApiClient:
    """Get or create k8s API client."""

    global _CLIENT  # noqa: PLW0603

    if _CLIENT and _CLIENT.rest_client.pool_manager.closed:
        _CLIENT = None

    if _CLIENT is None:  # pragma: no branch
        try:
            config.load_incluster_config()
        except Exception as ex:  # noqa: BLE001  # TODO: # pragma: no cover
            _LOGGER.debug("Failed to load incluster config", exc_info=ex)
            await config.load_kube_config()
        _CLIENT = ApiClient()

    return _CLIENT


async def get_v1_client() -> client.CoreV1Api:
    """Get v1 k8s client."""

    return client.CoreV1Api(await get_k8s_client())


async def get_v1_batch_client() -> client.BatchV1Api:
    """Get v1 k8s client."""

    return client.BatchV1Api(await get_k8s_client())


async def get_v1_ext_client() -> client.ApiextensionsV1Api:
    """Get v1 k8s client."""

    return client.ApiextensionsV1Api(await get_k8s_client())


async def get_crd_client() -> client.CustomObjectsApi:
    """Get crd k8s client."""

    return client.CustomObjectsApi(await get_k8s_client())
