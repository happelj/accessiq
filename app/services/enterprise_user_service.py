from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain.events import (
    CostCenterChanged,
    DepartmentChanged,
    DivisionChanged,
    DomainEvent,
    EmployeeNumberChanged,
    EnterpriseProfileCreated,
    EnterpriseProfileUpdated,
    ManagerChanged,
    OrganizationChanged,
    event_time,
)
from ..domain.publisher import publish_domain_events
from ..models import EnterpriseUserProfile, User
from .user_service import DEFAULT_PROVISIONED_DEPARTMENT

UNSET = object()

EnterpriseProfileChangeKind = Literal[
    "profile_created",
    "profile_updated",
    "employeeNumber",
    "department",
    "division",
    "organization",
    "costCenter",
    "manager",
]

ENTERPRISE_FIELDS = (
    ("employeeNumber", "employee_number"),
    ("department", "department"),
    ("division", "division"),
    ("organization", "organization"),
    ("costCenter", "cost_center"),
)


@dataclass(frozen=True)
class EnterpriseProfileMutation:
    employee_number: Any = UNSET
    department: Any = UNSET
    division: Any = UNSET
    organization: Any = UNSET
    cost_center: Any = UNSET
    manager_id: Any = UNSET

    def has_changes(self) -> bool:
        return any(
            value is not UNSET
            for value in (
                self.employee_number,
                self.department,
                self.division,
                self.organization,
                self.cost_center,
                self.manager_id,
            )
        )


@dataclass(frozen=True)
class EnterpriseProfileChange:
    kind: EnterpriseProfileChangeKind


class EnterpriseUserServiceError(Exception):
    """Base exception for reusable enterprise user service failures."""


class DuplicateEmployeeNumberError(EnterpriseUserServiceError):
    def __init__(
        self,
        employee_number: str,
        existing_profile: EnterpriseUserProfile,
    ) -> None:
        super().__init__(f"Employee number {employee_number!r} is already assigned")
        self.employee_number = employee_number
        self.existing_profile = existing_profile


class UnknownManagerError(EnterpriseUserServiceError):
    def __init__(self, manager_id: int) -> None:
        super().__init__(f"Manager {manager_id} was not found")
        self.manager_id = manager_id


class SelfManagerError(EnterpriseUserServiceError):
    def __init__(self, user_id: int) -> None:
        super().__init__("A user cannot be their own manager")
        self.user_id = user_id


class ManagerCycleError(EnterpriseUserServiceError):
    def __init__(self, user_id: int, manager_id: int) -> None:
        super().__init__("Manager assignment would create a cycle")
        self.user_id = user_id
        self.manager_id = manager_id


class EnterpriseUserService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.pending_events: list[DomainEvent] = []

    def create_enterprise_profile(
        self,
        user: User,
        mutation: EnterpriseProfileMutation | None,
    ) -> list[EnterpriseProfileChange]:
        if mutation is None:
            return []

        return self._apply_profile_mutation(user, mutation, replace=False)

    def update_enterprise_profile(
        self,
        user: User,
        mutation: EnterpriseProfileMutation | None,
    ) -> list[EnterpriseProfileChange]:
        if mutation is None:
            return []

        return self._apply_profile_mutation(user, mutation, replace=False)

    def replace_enterprise_profile(
        self,
        user: User,
        mutation: EnterpriseProfileMutation | None,
    ) -> list[EnterpriseProfileChange]:
        if mutation is None:
            return self._clear_enterprise_profile(user)

        return self._apply_profile_mutation(user, mutation, replace=True)

    def patch_enterprise_profile(
        self,
        user: User,
        mutation: EnterpriseProfileMutation | None,
    ) -> list[EnterpriseProfileChange]:
        if mutation is None:
            return []

        return self._apply_profile_mutation(user, mutation, replace=False)

    def validate_manager(self, user: User, manager_id: int | None) -> User | None:
        if manager_id is None:
            return None

        manager = self.db.get(User, manager_id)
        if manager is None:
            raise UnknownManagerError(manager_id)

        if manager.id == user.id:
            raise SelfManagerError(user.id)

        seen_user_ids = {user.id}
        current_manager = manager
        while current_manager.enterprise_profile is not None:
            next_manager_id = current_manager.enterprise_profile.manager_id
            if next_manager_id is None:
                return manager

            if next_manager_id == user.id:
                raise ManagerCycleError(user.id, manager.id)

            if next_manager_id in seen_user_ids:
                return manager

            seen_user_ids.add(next_manager_id)
            next_manager = self.db.get(User, next_manager_id)
            if next_manager is None:
                return manager

            current_manager = next_manager

        return manager

    def find_manager(self, manager_id: int | None) -> User | None:
        if manager_id is None:
            return None

        return self.db.get(User, manager_id)

    def publish_pending_events(self) -> None:
        publish_domain_events(self.pending_events)
        self.pending_events.clear()

    def _apply_profile_mutation(
        self,
        user: User,
        mutation: EnterpriseProfileMutation,
        *,
        replace: bool,
    ) -> list[EnterpriseProfileChange]:
        if not mutation.has_changes() and not replace:
            return []

        desired_values = self._desired_values(mutation, replace=replace)
        if not desired_values:
            return []

        profile = user.enterprise_profile
        created = False
        if profile is None:
            if all(value is None for value in desired_values.values()):
                return []

            profile = EnterpriseUserProfile(user=user)
            self.db.add(profile)
            self.db.flush()
            created = True

        changes: list[EnterpriseProfileChange] = []

        if "employee_number" in desired_values:
            employee_number = desired_values["employee_number"]
            if employee_number is not None:
                self._ensure_employee_number_available(
                    employee_number,
                    current_profile=profile,
                )

        if "manager_id" in desired_values:
            self.validate_manager(user, desired_values["manager_id"])

        for scim_name, column_name in ENTERPRISE_FIELDS:
            if column_name not in desired_values:
                continue

            new_value = desired_values[column_name]
            old_value = getattr(profile, column_name)
            if old_value == new_value:
                continue

            setattr(profile, column_name, new_value)
            changes.append(EnterpriseProfileChange(scim_name))
            self._append_attribute_event(user.id, scim_name, new_value)

            if scim_name == "department":
                user.department = new_value or DEFAULT_PROVISIONED_DEPARTMENT

        if "manager_id" in desired_values:
            new_manager_id = desired_values["manager_id"]
            if profile.manager_id != new_manager_id:
                profile.manager_id = new_manager_id
                changes.append(EnterpriseProfileChange("manager"))
                self.pending_events.append(
                    ManagerChanged(
                        occurred_at=event_time(),
                        user_id=user.id,
                        manager_id=new_manager_id,
                    )
                )

        if not changes:
            return []

        if created:
            changes.insert(0, EnterpriseProfileChange("profile_created"))
            self.pending_events.insert(
                0,
                EnterpriseProfileCreated(
                    occurred_at=event_time(),
                    user_id=user.id,
                ),
            )
        else:
            changes.insert(0, EnterpriseProfileChange("profile_updated"))
            self.pending_events.insert(
                0,
                EnterpriseProfileUpdated(
                    occurred_at=event_time(),
                    user_id=user.id,
                ),
            )

        self.db.flush()
        return changes

    def _clear_enterprise_profile(
        self,
        user: User,
    ) -> list[EnterpriseProfileChange]:
        profile = user.enterprise_profile
        if profile is None:
            return []

        mutation = EnterpriseProfileMutation(
            employee_number=None,
            department=None,
            division=None,
            organization=None,
            cost_center=None,
            manager_id=None,
        )
        return self._apply_profile_mutation(user, mutation, replace=False)

    def _desired_values(
        self,
        mutation: EnterpriseProfileMutation,
        *,
        replace: bool,
    ) -> dict[str, str | int | None]:
        values: dict[str, str | int | None] = {}
        mutation_values = {
            "employee_number": mutation.employee_number,
            "department": mutation.department,
            "division": mutation.division,
            "organization": mutation.organization,
            "cost_center": mutation.cost_center,
            "manager_id": mutation.manager_id,
        }

        for column_name, value in mutation_values.items():
            if value is UNSET:
                if replace:
                    values[column_name] = None
                continue

            values[column_name] = value

        return values

    def _ensure_employee_number_available(
        self,
        employee_number: str,
        *,
        current_profile: EnterpriseUserProfile,
    ) -> None:
        existing_profile = self.db.scalar(
            select(EnterpriseUserProfile).where(
                func.lower(EnterpriseUserProfile.employee_number)
                == employee_number.lower()
            )
        )
        if existing_profile is None:
            return

        if existing_profile.id == current_profile.id:
            return

        raise DuplicateEmployeeNumberError(employee_number, existing_profile)

    def _append_attribute_event(
        self,
        user_id: int,
        scim_name: str,
        value: str | int | None,
    ) -> None:
        if scim_name == "employeeNumber":
            self.pending_events.append(
                EmployeeNumberChanged(
                    occurred_at=event_time(),
                    user_id=user_id,
                    employee_number=value if isinstance(value, str) else None,
                )
            )
            return

        if scim_name == "department":
            self.pending_events.append(
                DepartmentChanged(
                    occurred_at=event_time(),
                    user_id=user_id,
                    department=value if isinstance(value, str) else None,
                )
            )
            return

        if scim_name == "division":
            self.pending_events.append(
                DivisionChanged(
                    occurred_at=event_time(),
                    user_id=user_id,
                    division=value if isinstance(value, str) else None,
                )
            )
            return

        if scim_name == "organization":
            self.pending_events.append(
                OrganizationChanged(
                    occurred_at=event_time(),
                    user_id=user_id,
                    organization=value if isinstance(value, str) else None,
                )
            )
            return

        if scim_name == "costCenter":
            self.pending_events.append(
                CostCenterChanged(
                    occurred_at=event_time(),
                    user_id=user_id,
                    cost_center=value if isinstance(value, str) else None,
                )
            )
