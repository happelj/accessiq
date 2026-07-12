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


@dataclass(frozen=True)
class EnterpriseProfileCreated(DomainEvent):
    user_id: int


@dataclass(frozen=True)
class EnterpriseProfileUpdated(DomainEvent):
    user_id: int


@dataclass(frozen=True)
class ManagerChanged(DomainEvent):
    user_id: int
    manager_id: int | None


@dataclass(frozen=True)
class DepartmentChanged(DomainEvent):
    user_id: int
    department: str | None


@dataclass(frozen=True)
class OrganizationChanged(DomainEvent):
    user_id: int
    organization: str | None


@dataclass(frozen=True)
class CostCenterChanged(DomainEvent):
    user_id: int
    cost_center: str | None


@dataclass(frozen=True)
class DivisionChanged(DomainEvent):
    user_id: int
    division: str | None


@dataclass(frozen=True)
class EmployeeNumberChanged(DomainEvent):
    user_id: int
    employee_number: str | None


def event_time() -> datetime:
    return datetime.now(UTC)
