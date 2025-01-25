# noqa: A005
"""ARK Operator types."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from kopf import (
        Annotations,
        Body,
        BodyEssence,
        Diff,
        Headers,
        Labels,
        Logger,
        Meta,
        OperatorSettings,
        Patch,
        Resource,
        Spec,
        SSLPeer,
        Status,
        UserInfo,
    )


class ClusterStage(StrEnum):
    """Cluster status stage."""

    CREATE_PVC = "create_pvc"
    INIT_PVC = "init_pvc"
    UPDATE_PVC = "update_pvc"


class ActivityEvent(TypedDict):
    """Kopf activity event."""

    settings: OperatorSettings
    retry: int
    started: datetime
    runtime: timedelta
    logger: Logger
    memo: Any
    param: Any


class ChangeEvent(TypedDict):
    """Kopf change event."""

    retry: int
    started: datetime
    runtime: timedelta
    annotations: Annotations
    labels: Labels
    body: Body
    meta: Meta
    spec: Spec
    status: Status
    resource: Resource
    uid: str | None
    name: str | None
    namespace: str | None
    patch: Patch
    reason: str
    diff: Diff
    old: BodyEssence | None | Any
    new: BodyEssence | None | Any
    logger: Logger
    memo: Any
    param: Any


class WebhookEvent(TypedDict):
    """Kopf webhook event."""

    dryrun: bool
    warnings: list[str]
    subresource: str | None
    userinfo: UserInfo
    sslpeer: SSLPeer
    headers: Headers
    labels: Labels
    annotations: Annotations
    body: Body
    meta: Meta
    spec: Spec
    status: Status
    resource: Resource
    uid: str | None
    name: str | None
    namespace: str | None
    patch: Patch
    logger: Logger
    memo: Any
    param: Any


class TimerEvent(TypedDict):
    """Kopf timer event."""

    annotations: Annotations
    labels: Labels
    body: Body
    meta: Meta
    spec: Spec
    status: Status
    resource: Resource
    uid: str | None
    name: str | None
    namespace: str | None
    patch: Patch
    logger: Logger
    memo: Any
    param: Any
