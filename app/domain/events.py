from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class DomainEvent:
    occurred_at: datetime


@dataclass(frozen=True)
class GroupCreated(DomainEvent):
    group_id: int
    display_name: str


@dataclass(frozen=True)
class GroupUpdated(DomainEvent):
    group_id: int
    display_name: str


@dataclass(frozen=True)
class GroupMembershipAdded(DomainEvent):
    group_id: int
    user_id: int


@dataclass(frozen=True)
class GroupMembershipRemoved(DomainEvent):
    group_id: int
    user_id: int


@dataclass(frozen=True)
class GroupMembershipReplaced(DomainEvent):
    group_id: int
    user_ids: tuple[int, ...]


@dataclass(frozen=True)
class UserProvisioned(DomainEvent):
    user_id: int
    user_name: str


def event_time() -> datetime:
    return datetime.now(UTC)
