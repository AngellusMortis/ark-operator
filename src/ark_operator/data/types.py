"""ARK Operator types."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypedDict, TypeVar

from typing_extensions import NotRequired

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from kopf import (
        Annotations,
        Body,
        BodyEssence,
        Diff,
        Labels,
        Logger,
        Meta,
        OperatorSettings,
        Patch,
        Resource,
        Status,
    )

T = TypeVar("T")


class ArkServerSpec(TypedDict):
    """ArkCluster.spec.server CRD spec."""

    steamStorageClass: NotRequired[str]
    storageClass: NotRequired[str]
    size: NotRequired[int | str]
    maps: NotRequired[list[str]]


class ArkDataSpec(TypedDict):
    """ArkCluster.spec.data CRD spec."""

    storageClass: NotRequired[str]
    size: NotRequired[int | str]


class ArkClusterSpec(TypedDict):
    """ArkCluster.spec CRD spec."""

    server: NotRequired[ArkServerSpec]
    data: NotRequired[ArkDataSpec]


class ActivityEvent(TypedDict):
    """Kopf activity event."""

    settings: OperatorSettings
    retry: int
    started: datetime
    runtime: timedelta
    logger: Logger
    memo: Any
    param: Any


class ChangeEvent(Generic[T], TypedDict):
    """Kopf change event."""

    retry: int
    started: datetime
    runtime: timedelta
    annotations: Annotations
    labels: Labels
    body: Body
    meta: Meta
    spec: T
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
