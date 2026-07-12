from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql.elements import ColumnElement

from ..audit_service import create_audit_event
from ..domain.events import (
    DelegatedAccessDenied,
    DelegatedAccessGranted,
    DelegationAssigned,
    DelegationRemoved,
    DomainEvent,
    event_time,
)
from ..domain.publisher import publish_domain_events
from ..models import Application, Entitlement, Group, User
from ..roles import normalize_operator_role
from .enums import DelegatedAction, DelegationRole, DelegationScopeType
from .models import DelegationAssignment
from .validation import role_supports_access_change, role_supports_scope

ACTION_DELEGATION_ASSIGNED = "delegation_assigned"
ACTION_DELEGATION_REMOVED = "delegation_removed"
ACTION_DELEGATED_ACTION_ALLOWED = "delegated_action_allowed"
ACTION_DELEGATED_ACTION_DENIED = "delegated_action_denied"

GLOBAL_ADMIN_ROLES = {"security_admin", "iam_admin"}
SUPPORTED_DELEGATION_SORT_FIELDS: dict[str, ColumnElement[Any]] = {
    "id": DelegationAssignment.id,
    "created_at": DelegationAssignment.created_at,
    "expires_at": DelegationAssignment.expires_at,
    "scope_type": DelegationAssignment.scope_type,
    "delegation_role": DelegationAssignment.delegation_role,
}
SUPPORTED_SORT_ORDERS = {"ascending", "descending"}


@dataclass(frozen=True)
class DelegationAssignmentFilters:
    delegate_user_id: int | None = None
    scope_type: str | None = None
    scope_id: int | None = None
    delegation_role: str | None = None
    active: bool | None = None


@dataclass(frozen=True)
class DelegationAuthorization:
    allowed: bool
    delegated: bool
    reason: str
    assignment: DelegationAssignment | None = None

    @property
    def delegation_role(self) -> str | None:
        if self.assignment is None:
            return None

        return self.assignment.delegation_role


class DelegationServiceError(Exception):
    """Base exception for delegated administration service failures."""


class DelegationAssignmentNotFoundError(DelegationServiceError):
    def __init__(self, assignment_id: int) -> None:
        super().__init__(f"Delegation assignment {assignment_id} was not found")
        self.assignment_id = assignment_id


class DelegationDelegateNotFoundError(DelegationServiceError):
    def __init__(self, delegate_user_id: int) -> None:
        super().__init__(f"Delegate user {delegate_user_id} was not found")
        self.delegate_user_id = delegate_user_id


class InactiveDelegateUserError(DelegationServiceError):
    def __init__(self, delegate_user_id: int) -> None:
        super().__init__(f"Delegate user {delegate_user_id} is inactive")
        self.delegate_user_id = delegate_user_id


class DelegationScopeNotFoundError(DelegationServiceError):
    def __init__(self, scope_type: str, scope_id: int) -> None:
        super().__init__(f"{scope_type} scope {scope_id} was not found")
        self.scope_type = scope_type
        self.scope_id = scope_id


class InvalidDelegationScopeError(DelegationServiceError):
    def __init__(
        self,
        scope_type: DelegationScopeType,
        delegation_role: DelegationRole,
    ) -> None:
        super().__init__(
            f"{delegation_role.value} cannot be assigned to {scope_type.value} scope"
        )
        self.scope_type = scope_type
        self.delegation_role = delegation_role


class DuplicateDelegationAssignmentError(DelegationServiceError):
    def __init__(
        self,
        delegate_user_id: int,
        scope_type: DelegationScopeType,
        scope_id: int,
        delegation_role: DelegationRole,
    ) -> None:
        super().__init__(
            "Delegation assignment already exists for "
            f"user={delegate_user_id}, scope={scope_type.value}:{scope_id}, "
            f"role={delegation_role.value}"
        )
        self.delegate_user_id = delegate_user_id
        self.scope_type = scope_type
        self.scope_id = scope_id
        self.delegation_role = delegation_role


class ExpiredDelegationAssignmentError(DelegationServiceError):
    def __init__(self) -> None:
        super().__init__("Delegation assignment expiration must be in the future")


class InactiveDelegationAssignmentError(DelegationServiceError):
    def __init__(self, assignment_id: int) -> None:
        super().__init__(f"Delegation assignment {assignment_id} is inactive")
        self.assignment_id = assignment_id


class UnsupportedDelegationSortFieldError(DelegationServiceError):
    def __init__(self, sort_by: str) -> None:
        super().__init__(f"Unsupported delegation sort field: {sort_by}")
        self.sort_by = sort_by


class UnsupportedDelegationSortOrderError(DelegationServiceError):
    def __init__(self, sort_order: str) -> None:
        super().__init__(f"Unsupported delegation sort order: {sort_order}")
        self.sort_order = sort_order


class DelegationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.pending_events: list[DomainEvent] = []

    def assign_delegate(
        self,
        *,
        delegate_user_id: int,
        scope_type: DelegationScopeType,
        scope_id: int,
        delegation_role: DelegationRole,
        actor: User,
        expires_at: datetime | None = None,
    ) -> DelegationAssignment:
        delegate = self.db.get(User, delegate_user_id)
        if delegate is None:
            raise DelegationDelegateNotFoundError(delegate_user_id)
        if not delegate.active:
            raise InactiveDelegateUserError(delegate_user_id)
        if expires_at is not None and _is_expired(expires_at):
            raise ExpiredDelegationAssignmentError()

        self.validate_scope(scope_type, scope_id, delegation_role)
        self._prevent_duplicate_assignment(
            delegate_user_id=delegate_user_id,
            scope_type=scope_type,
            scope_id=scope_id,
            delegation_role=delegation_role,
        )

        assignment = DelegationAssignment(
            delegate_user_id=delegate_user_id,
            scope_type=scope_type.value,
            scope_id=scope_id,
            delegation_role=delegation_role.value,
            created_by=actor.id,
            expires_at=expires_at,
            active=True,
        )
        self.db.add(assignment)
        self.db.flush()
        self._record_assignment_audit(
            assignment,
            actor=actor,
            action=ACTION_DELEGATION_ASSIGNED,
            result="succeeded",
            reason=f"Delegation assignment {assignment.id} created",
        )
        self.pending_events.append(
            DelegationAssigned(
                occurred_at=event_time(),
                assignment_id=assignment.id,
                delegate_user_id=assignment.delegate_user_id,
                scope_type=assignment.scope_type,
                scope_id=assignment.scope_id,
                delegation_role=assignment.delegation_role,
            )
        )

        return assignment

    def remove_delegate(
        self,
        assignment_id: int,
        *,
        actor: User,
    ) -> DelegationAssignment:
        assignment = self.lookup_assignment(assignment_id)
        if not assignment.active:
            raise InactiveDelegationAssignmentError(assignment_id)

        assignment.active = False
        self.db.flush()
        self._record_assignment_audit(
            assignment,
            actor=actor,
            action=ACTION_DELEGATION_REMOVED,
            result="succeeded",
            reason=f"Delegation assignment {assignment.id} removed",
        )
        self.pending_events.append(
            DelegationRemoved(
                occurred_at=event_time(),
                assignment_id=assignment.id,
                delegate_user_id=assignment.delegate_user_id,
                scope_type=assignment.scope_type,
                scope_id=assignment.scope_id,
                delegation_role=assignment.delegation_role,
            )
        )

        return assignment

    def lookup_assignment(self, assignment_id: int) -> DelegationAssignment:
        assignment = self.db.scalar(
            _assignment_query().where(DelegationAssignment.id == assignment_id)
        )
        if assignment is None:
            raise DelegationAssignmentNotFoundError(assignment_id)

        return assignment

    def list_assignments(
        self,
        *,
        filters: DelegationAssignmentFilters,
        offset: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "descending",
    ) -> list[DelegationAssignment]:
        statement = _assignment_query()
        if filters.delegate_user_id is not None:
            statement = statement.where(
                DelegationAssignment.delegate_user_id == filters.delegate_user_id
            )
        if filters.scope_type is not None:
            statement = statement.where(
                DelegationAssignment.scope_type == filters.scope_type
            )
        if filters.scope_id is not None:
            statement = statement.where(DelegationAssignment.scope_id == filters.scope_id)
        if filters.delegation_role is not None:
            statement = statement.where(
                DelegationAssignment.delegation_role == filters.delegation_role
            )
        if filters.active is not None:
            statement = statement.where(DelegationAssignment.active == filters.active)

        statement = _apply_sorting(
            statement,
            sort_by=sort_by or "created_at",
            sort_order=sort_order,
        )

        return list(
            self.db.execute(statement.offset(offset).limit(limit))
            .unique()
            .scalars()
            .all()
        )

    def validate_scope(
        self,
        scope_type: DelegationScopeType,
        scope_id: int,
        delegation_role: DelegationRole,
    ) -> None:
        if not role_supports_scope(scope_type, delegation_role):
            raise InvalidDelegationScopeError(scope_type, delegation_role)

        if scope_type == DelegationScopeType.APPLICATION:
            if self.db.get(Application, scope_id) is None:
                raise DelegationScopeNotFoundError(scope_type.value, scope_id)
            return

        if scope_type == DelegationScopeType.ENTITLEMENT:
            if self.db.get(Entitlement, scope_id) is None:
                raise DelegationScopeNotFoundError(scope_type.value, scope_id)
            return

        if scope_type == DelegationScopeType.GROUP:
            if self.db.get(Group, scope_id) is None:
                raise DelegationScopeNotFoundError(scope_type.value, scope_id)
            return

    def has_permission(
        self,
        *,
        delegate_user_id: int,
        action: DelegatedAction,
        entitlement: Entitlement,
    ) -> DelegationAssignment | None:
        del action
        for assignment in self.find_effective_delegations(
            delegate_user_id=delegate_user_id
        ):
            if not role_supports_access_change(assignment.delegation_role):
                continue

            if _assignment_matches_entitlement(assignment, entitlement):
                return assignment

        return None

    def find_effective_delegations(
        self,
        *,
        delegate_user_id: int,
    ) -> list[DelegationAssignment]:
        now = _utc_now()
        return list(
            self.db.scalars(
                _assignment_query()
                .where(
                    DelegationAssignment.delegate_user_id == delegate_user_id,
                    DelegationAssignment.active.is_(True),
                    or_(
                        DelegationAssignment.expires_at.is_(None),
                        DelegationAssignment.expires_at > now,
                    ),
                )
                .order_by(DelegationAssignment.id)
            ).all()
        )

    def authorize_access_action(
        self,
        *,
        actor: User,
        target_user: User,
        entitlement: Entitlement,
        action: DelegatedAction,
    ) -> DelegationAuthorization:
        actor_role = normalize_operator_role(actor.operator_role)
        if actor_role in GLOBAL_ADMIN_ROLES:
            return DelegationAuthorization(
                allowed=True,
                delegated=False,
                reason="Global administrative role",
            )

        assignment = self.has_permission(
            delegate_user_id=actor.id,
            action=action,
            entitlement=entitlement,
        )
        if assignment is None:
            reason = "No active delegation permits this action"
            self._record_action_audit(
                actor=actor,
                target_user=target_user,
                entitlement=entitlement,
                action=ACTION_DELEGATED_ACTION_DENIED,
                result="denied",
                reason=reason,
            )
            self.record_delegated_access_denied(
                actor=actor,
                target_user=target_user,
                entitlement=entitlement,
                action=action,
                reason=reason,
                assignment=None,
            )
            return DelegationAuthorization(
                allowed=False,
                delegated=False,
                reason=reason,
            )

        reason = f"Delegation assignment {assignment.id} permits this action"
        self._record_action_audit(
            actor=actor,
            target_user=target_user,
            entitlement=entitlement,
            action=ACTION_DELEGATED_ACTION_ALLOWED,
            result="allowed",
            reason=reason,
        )
        return DelegationAuthorization(
            allowed=True,
            delegated=True,
            reason=reason,
            assignment=assignment,
        )

    def record_delegated_access_granted(
        self,
        *,
        actor: User,
        target_user: User,
        entitlement: Entitlement,
        action: DelegatedAction,
        assignment: DelegationAssignment,
    ) -> None:
        self.pending_events.append(
            DelegatedAccessGranted(
                occurred_at=event_time(),
                assignment_id=assignment.id,
                delegate_user_id=actor.id,
                target_user_id=target_user.id,
                entitlement_id=entitlement.id,
                application_id=entitlement.application_id,
                action=action.value,
            )
        )

    def record_delegated_access_denied(
        self,
        *,
        actor: User,
        target_user: User,
        entitlement: Entitlement,
        action: DelegatedAction,
        reason: str,
        assignment: DelegationAssignment | None,
    ) -> None:
        self.pending_events.append(
            DelegatedAccessDenied(
                occurred_at=event_time(),
                assignment_id=assignment.id if assignment is not None else None,
                delegate_user_id=actor.id,
                target_user_id=target_user.id,
                entitlement_id=entitlement.id,
                application_id=entitlement.application_id,
                action=action.value,
                reason=reason,
            )
        )

    def publish_pending_events(self) -> None:
        publish_domain_events(self.pending_events)
        self.pending_events.clear()

    def _prevent_duplicate_assignment(
        self,
        *,
        delegate_user_id: int,
        scope_type: DelegationScopeType,
        scope_id: int,
        delegation_role: DelegationRole,
    ) -> None:
        now = _utc_now()
        existing_assignment = self.db.scalar(
            select(DelegationAssignment).where(
                DelegationAssignment.delegate_user_id == delegate_user_id,
                DelegationAssignment.scope_type == scope_type.value,
                DelegationAssignment.scope_id == scope_id,
                DelegationAssignment.delegation_role == delegation_role.value,
                DelegationAssignment.active.is_(True),
                or_(
                    DelegationAssignment.expires_at.is_(None),
                    DelegationAssignment.expires_at > now,
                ),
            )
        )
        if existing_assignment is not None:
            raise DuplicateDelegationAssignmentError(
                delegate_user_id,
                scope_type,
                scope_id,
                delegation_role,
            )

    def _record_assignment_audit(
        self,
        assignment: DelegationAssignment,
        *,
        actor: User,
        action: str,
        result: str,
        reason: str,
    ) -> None:
        application_id, entitlement_id = self._audit_reference_for_assignment(
            assignment
        )
        create_audit_event(
            self.db,
            requester_id=actor.id,
            target_user_id=assignment.delegate_user_id,
            action=action,
            application_id=application_id,
            entitlement_id=entitlement_id,
            result=result,
            reason=reason,
        )

    def _record_action_audit(
        self,
        *,
        actor: User,
        target_user: User,
        entitlement: Entitlement,
        action: str,
        result: str,
        reason: str,
    ) -> None:
        create_audit_event(
            self.db,
            requester_id=actor.id,
            target_user_id=target_user.id,
            action=action,
            application_id=entitlement.application_id,
            entitlement_id=entitlement.id,
            result=result,
            reason=reason,
        )

    def _audit_reference_for_assignment(
        self,
        assignment: DelegationAssignment,
    ) -> tuple[int, int]:
        scope_type = DelegationScopeType(assignment.scope_type)
        if scope_type == DelegationScopeType.ENTITLEMENT:
            entitlement = self.db.get(Entitlement, assignment.scope_id)
            if entitlement is None:
                raise DelegationScopeNotFoundError(scope_type.value, assignment.scope_id)
            return entitlement.application_id, entitlement.id

        if scope_type == DelegationScopeType.APPLICATION:
            entitlement = self.db.scalar(
                select(Entitlement)
                .where(Entitlement.application_id == assignment.scope_id)
                .order_by(Entitlement.id)
            )
            if entitlement is None:
                raise DelegationScopeNotFoundError(scope_type.value, assignment.scope_id)
            return entitlement.application_id, entitlement.id

        fallback = self.db.scalar(
            select(Entitlement)
            .join(Application)
            .where(
                Application.slug == "scim-provisioning",
                Entitlement.slug == "group-lifecycle",
            )
        )
        if fallback is None:
            raise DelegationScopeNotFoundError(scope_type.value, assignment.scope_id)

        return fallback.application_id, fallback.id


def _assignment_query() -> Select[tuple[DelegationAssignment]]:
    return select(DelegationAssignment).options(
        joinedload(DelegationAssignment.delegate),
        joinedload(DelegationAssignment.creator),
    )


def _assignment_matches_entitlement(
    assignment: DelegationAssignment,
    entitlement: Entitlement,
) -> bool:
    scope_type = DelegationScopeType(assignment.scope_type)
    if scope_type == DelegationScopeType.APPLICATION:
        return assignment.scope_id == entitlement.application_id

    if scope_type == DelegationScopeType.ENTITLEMENT:
        return assignment.scope_id == entitlement.id

    return False


def _apply_sorting(
    statement: Select[Any],
    *,
    sort_by: str,
    sort_order: str,
) -> Select[Any]:
    if sort_order not in SUPPORTED_SORT_ORDERS:
        raise UnsupportedDelegationSortOrderError(sort_order)

    sort_expression = SUPPORTED_DELEGATION_SORT_FIELDS.get(sort_by)
    if sort_expression is None:
        raise UnsupportedDelegationSortFieldError(sort_by)

    if sort_order == "descending":
        return statement.order_by(sort_expression.desc(), DelegationAssignment.id.desc())

    return statement.order_by(sort_expression.asc(), DelegationAssignment.id.asc())


def _is_expired(expires_at: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    return expires_at <= _utc_now()


def _utc_now() -> datetime:
    return datetime.now(UTC)
