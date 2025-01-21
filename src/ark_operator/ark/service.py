"""ARK service utils."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ark_operator.data import ArkClusterSpec


async def get_cluster_host(
    *,
    name: str,  # noqa: ARG001
    namespace: str,  # noqa: ARG001
    spec: ArkClusterSpec,
) -> str | None:
    """Get host for ArkCluster."""

    if spec.service.load_balancer_ip:
        return str(spec.service.load_balancer_ip)
    if spec.server.load_balancer_ip:
        return str(spec.server.load_balancer_ip)

    return None
