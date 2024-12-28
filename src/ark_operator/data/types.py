"""ARK Operator types."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

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
        Spec,
        Status,
    )


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
