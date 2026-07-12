from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import status
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..audit_service import create_audit_event
from ..models import Application, Entitlement, User
from ..services.enterprise_user_service import (
    DuplicateEmployeeNumberError,
    EnterpriseProfileChange,
    EnterpriseProfileMutation,
    EnterpriseUserService,
    ManagerCycleError,
    SelfManagerError,
    UnknownManagerError,
    UNSET,
)
from ..services.user_service import (
    DuplicateUserNameError,
    UserMutation,
    UserNotFoundError,
    UserService,
)
from .constants import SCIM_SCHEMA_ENTERPRISE_USER, SCIM_SCHEMA_USER
from .errors import ScimHTTPException, raise_scim_error
from .users import build_user_location, user_to_scim_resource

SCIM_PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
SCIM_AUDIT_APPLICATION_SLUG = "scim-provisioning"
SCIM_AUDIT_ENTITLEMENT_SLUG = "user-lifecycle"
SCIM_ENTERPRISE_AUDIT_ENTITLEMENT_SLUG = "enterprise-user-extension"

ACTION_CREATE = "scim_user_create"
ACTION_UPDATE = "scim_user_update"
ACTION_DEACTIVATE = "scim_user_deactivate"
ACTION_FAILURE = "scim_user_provisioning_failure"
ACTION_ENTERPRISE_PROFILE_CREATE = "scim_enterprise_profile_create"
ACTION_ENTERPRISE_PROFILE_UPDATE = "scim_enterprise_profile_update"
ACTION_ENTERPRISE_MANAGER_CHANGE = "scim_enterprise_manager_change"
ACTION_ENTERPRISE_DEPARTMENT_CHANGE = "scim_enterprise_department_change"
ACTION_ENTERPRISE_ORGANIZATION_CHANGE = "scim_enterprise_organization_change"
ACTION_ENTERPRISE_COST_CENTER_CHANGE = "scim_enterprise_cost_center_change"
ACTION_ENTERPRISE_DIVISION_CHANGE = "scim_enterprise_division_change"
ACTION_ENTERPRISE_EMPLOYEE_NUMBER_CHANGE = "scim_enterprise_employee_number_change"
ACTION_ENTERPRISE_FAILURE = "scim_enterprise_provisioning_failure"

EMAIL_ADAPTER = TypeAdapter(EmailStr)
PATCH_PATHS = {
    "username": "userName",
    "displayname": "displayName",
    "active": "active",
}
ENTERPRISE_PATCH_PATHS = {
    "employeenumber": "employeeNumber",
    "department": "department",
    "division": "division",
    "organization": "organization",
    "costcenter": "costCenter",
    "manager": "manager",
    "manager.value": "manager",
}
ENTERPRISE_CHANGE_AUDIT = {
    "profile_created": (
        ACTION_ENTERPRISE_PROFILE_CREATE,
        "Enterprise profile created",
    ),
    "profile_updated": (
        ACTION_ENTERPRISE_PROFILE_UPDATE,
        "Enterprise profile updated",
    ),
    "employeeNumber": (
        ACTION_ENTERPRISE_EMPLOYEE_NUMBER_CHANGE,
        "Employee number changed",
    ),
    "department": (
        ACTION_ENTERPRISE_DEPARTMENT_CHANGE,
        "Department changed",
    ),
    "division": (
        ACTION_ENTERPRISE_DIVISION_CHANGE,
        "Division changed",
    ),
    "organization": (
        ACTION_ENTERPRISE_ORGANIZATION_CHANGE,
        "Organization changed",
    ),
    "costCenter": (
        ACTION_ENTERPRISE_COST_CENTER_CHANGE,
        "Cost center changed",
    ),
    "manager": (
        ACTION_ENTERPRISE_MANAGER_CHANGE,
        "Manager changed",
    ),
}


@dataclass(frozen=True)
class ScimUserPayload:
    user_name: str
    display_name: str
    active: bool
    enterprise_profile: EnterpriseProfileMutation | None = None


@dataclass(frozen=True)
class ScimUserPatch:
    user_mutation: UserMutation
    enterprise_profile: EnterpriseProfileMutation | None = None


@dataclass(frozen=True)
class ScimProvisioningResult:
    resource: dict[str, Any]
    location: str


def create_scim_user(
    *,
    db: Session,
    actor: User,
    payload: Any,
    base_url: str,
) -> ScimProvisioningResult:
    try:
        user_data = _parse_user_payload(payload, active_default=True)
    except ScimHTTPException as exc:
        _audit_scim_exception_and_raise(
            db,
            actor=actor,
            target_user=None,
            reason=str(exc.detail),
            status_code=exc.status_code,
            scim_type=exc.scim_type,
        )

    service = UserService(db)
    enterprise_service = EnterpriseUserService(db)

    try:
        user = service.create_user(
            user_name=user_data.user_name,
            display_name=user_data.display_name,
            active=user_data.active,
        )
        enterprise_changes = enterprise_service.create_enterprise_profile(
            user,
            user_data.enterprise_profile,
        )
        _record_provisioning_audit(
            db,
            actor=actor,
            target_user=user,
            action=ACTION_CREATE,
            result="succeeded",
            reason="User created",
        )
        _record_enterprise_audits(
            db,
            actor=actor,
            target_user=user,
            changes=enterprise_changes,
        )
        db.commit()
        service.publish_pending_events()
        enterprise_service.publish_pending_events()
        db.refresh(user)
    except DuplicateUserNameError as exc:
        db.rollback()
        _audit_and_raise(
            db,
            actor=actor,
            target_user=exc.existing_user,
            action=ACTION_FAILURE,
            reason="Duplicate userName",
            status_code=status.HTTP_409_CONFLICT,
            scim_type="uniqueness",
        )
    except (
        DuplicateEmployeeNumberError,
        UnknownManagerError,
        SelfManagerError,
        ManagerCycleError,
    ) as exc:
        db.rollback()
        _audit_enterprise_error_and_raise(
            db,
            actor=actor,
            target_user=None,
            exc=exc,
        )
    except (IntegrityError, SQLAlchemyError) as exc:
        db.rollback()
        _raise_database_error(exc)

    location = build_user_location(base_url=base_url, user_id=user.id)
    return ScimProvisioningResult(
        resource=user_to_scim_resource(user, base_url=base_url),
        location=location,
    )


def replace_scim_user(
    *,
    db: Session,
    actor: User,
    user_id: str,
    payload: Any,
    base_url: str,
) -> ScimProvisioningResult:
    try:
        user_data = _parse_user_payload(payload, active_default=True)
    except ScimHTTPException as exc:
        _audit_scim_exception_and_raise(
            db,
            actor=actor,
            target_user=None,
            reason=str(exc.detail),
            status_code=exc.status_code,
            scim_type=exc.scim_type,
        )

    service = UserService(db)
    enterprise_service = EnterpriseUserService(db)

    try:
        user = service.replace_user(
            user_id,
            user_name=user_data.user_name,
            display_name=user_data.display_name,
            active=user_data.active,
        )
        enterprise_changes = enterprise_service.replace_enterprise_profile(
            user,
            user_data.enterprise_profile,
        )
        _record_provisioning_audit(
            db,
            actor=actor,
            target_user=user,
            action=_successful_update_action(user),
            result="succeeded",
            reason=_successful_update_reason(user),
        )
        _record_enterprise_audits(
            db,
            actor=actor,
            target_user=user,
            changes=enterprise_changes,
        )
        db.commit()
        enterprise_service.publish_pending_events()
        db.refresh(user)
    except UserNotFoundError:
        db.rollback()
        _audit_and_raise(
            db,
            actor=actor,
            target_user=None,
            action=ACTION_FAILURE,
            reason=f"User {user_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    except DuplicateUserNameError as exc:
        db.rollback()
        _audit_and_raise(
            db,
            actor=actor,
            target_user=exc.existing_user,
            action=ACTION_FAILURE,
            reason="Duplicate userName",
            status_code=status.HTTP_409_CONFLICT,
            scim_type="uniqueness",
        )
    except (
        DuplicateEmployeeNumberError,
        UnknownManagerError,
        SelfManagerError,
        ManagerCycleError,
    ) as exc:
        db.rollback()
        _audit_enterprise_error_and_raise(
            db,
            actor=actor,
            target_user=service.find_user(user_id),
            exc=exc,
        )
    except (IntegrityError, SQLAlchemyError) as exc:
        db.rollback()
        _raise_database_error(exc)

    return ScimProvisioningResult(
        resource=user_to_scim_resource(user, base_url=base_url),
        location=build_user_location(base_url=base_url, user_id=user.id),
    )


def patch_scim_user(
    *,
    db: Session,
    actor: User,
    user_id: str,
    payload: Any,
    base_url: str,
) -> ScimProvisioningResult:
    service = UserService(db)
    enterprise_service = EnterpriseUserService(db)

    try:
        current_user = service.find_user(user_id)
        if current_user is None:
            raise UserNotFoundError(user_id)

        try:
            patch = _parse_patch_payload(payload, current_user=current_user)
        except ScimHTTPException as exc:
            _audit_scim_exception_and_raise(
                db,
                actor=actor,
                target_user=current_user,
                reason=str(exc.detail),
                status_code=exc.status_code,
                scim_type=exc.scim_type,
            )

        user = service.patch_user(user_id, patch.user_mutation)
        enterprise_changes = enterprise_service.patch_enterprise_profile(
            user,
            patch.enterprise_profile,
        )
        _record_provisioning_audit(
            db,
            actor=actor,
            target_user=user,
            action=_successful_update_action(user),
            result="succeeded",
            reason=_successful_update_reason(user),
        )
        _record_enterprise_audits(
            db,
            actor=actor,
            target_user=user,
            changes=enterprise_changes,
        )
        db.commit()
        enterprise_service.publish_pending_events()
        db.refresh(user)
    except UserNotFoundError:
        db.rollback()
        _audit_and_raise(
            db,
            actor=actor,
            target_user=None,
            action=ACTION_FAILURE,
            reason=f"User {user_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    except DuplicateUserNameError as exc:
        db.rollback()
        _audit_and_raise(
            db,
            actor=actor,
            target_user=exc.existing_user,
            action=ACTION_FAILURE,
            reason="Duplicate userName",
            status_code=status.HTTP_409_CONFLICT,
            scim_type="uniqueness",
        )
    except (
        DuplicateEmployeeNumberError,
        UnknownManagerError,
        SelfManagerError,
        ManagerCycleError,
    ) as exc:
        db.rollback()
        _audit_enterprise_error_and_raise(
            db,
            actor=actor,
            target_user=service.find_user(user_id),
            exc=exc,
        )
    except (IntegrityError, SQLAlchemyError) as exc:
        db.rollback()
        _raise_database_error(exc)

    return ScimProvisioningResult(
        resource=user_to_scim_resource(user, base_url=base_url),
        location=build_user_location(base_url=base_url, user_id=user.id),
    )


def _parse_user_payload(payload: Any, *, active_default: bool) -> ScimUserPayload:
    if not isinstance(payload, dict):
        _raise_invalid_payload("SCIM User payload must be a JSON object")

    user_name = _parse_user_name(payload.get("userName"))
    display_name = _parse_display_name(payload)
    active = _parse_active(payload.get("active", active_default))
    enterprise_profile = _parse_enterprise_profile_payload(
        payload.get(SCIM_SCHEMA_ENTERPRISE_USER, UNSET)
    )

    return ScimUserPayload(
        user_name=user_name,
        display_name=display_name,
        active=active,
        enterprise_profile=enterprise_profile,
    )


def _parse_patch_payload(
    payload: Any,
    *,
    current_user: User,
) -> ScimUserPatch:
    if not isinstance(payload, dict):
        _raise_invalid_payload("SCIM PATCH payload must be a JSON object")

    operations = payload.get("Operations")
    if not isinstance(operations, list) or not operations:
        _raise_invalid_payload("SCIM PATCH requires a non-empty Operations array")

    patch = ScimUserPatch(user_mutation=UserMutation())
    for operation in operations:
        patch = _apply_patch_operation(
            patch,
            operation=operation,
            current_user=current_user,
        )

    return patch


def _apply_patch_operation(
    patch: ScimUserPatch,
    *,
    operation: Any,
    current_user: User,
) -> ScimUserPatch:
    if not isinstance(operation, dict):
        _raise_invalid_payload("Each PATCH operation must be an object")

    raw_op = operation.get("op")
    if not isinstance(raw_op, str):
        _raise_invalid_payload("Each PATCH operation requires an op")

    op = raw_op.lower()
    if op not in {"add", "replace", "remove"}:
        _raise_invalid_payload(f"Unsupported PATCH operation: {raw_op}")

    raw_path = operation.get("path")
    if raw_path is None:
        if op == "remove":
            _raise_invalid_payload("PATCH remove requires a path")

        value = operation.get("value")
        if not isinstance(value, dict):
            _raise_invalid_payload("PATCH operation without path requires object value")

        for attribute, attribute_value in value.items():
            patch = _apply_attribute_patch(
                patch,
                op=op,
                path=str(attribute),
                value=attribute_value,
                current_user=current_user,
            )

        return patch

    if not isinstance(raw_path, str):
        _raise_invalid_path("PATCH path must be a string")

    value = operation.get("value")
    if op in {"add", "replace"} and "value" not in operation:
        _raise_invalid_payload("PATCH add and replace operations require value")

    return _apply_attribute_patch(
        patch,
        op=op,
        path=raw_path,
        value=value,
        current_user=current_user,
    )


def _apply_attribute_patch(
    patch: ScimUserPatch,
    *,
    op: str,
    path: str,
    value: Any,
    current_user: User,
) -> ScimUserPatch:
    enterprise_path = _normalize_enterprise_patch_path(path)
    if enterprise_path is not None:
        return _apply_enterprise_attribute_patch(
            patch,
            op=op,
            path=enterprise_path,
            value=value,
        )

    normalized_path = PATCH_PATHS.get(path.lower())
    if normalized_path is None:
        _raise_invalid_path(f"Unsupported PATCH path: {path}")

    if op == "remove":
        return ScimUserPatch(
            user_mutation=_remove_attribute(
                patch.user_mutation,
                path=normalized_path,
                current_user=current_user,
            ),
            enterprise_profile=patch.enterprise_profile,
        )

    mutation = patch.user_mutation
    if normalized_path == "userName":
        return ScimUserPatch(
            user_mutation=UserMutation(
                user_name=_parse_user_name(value),
                display_name=mutation.display_name,
                active=mutation.active,
            ),
            enterprise_profile=patch.enterprise_profile,
        )

    if normalized_path == "displayName":
        return ScimUserPatch(
            user_mutation=UserMutation(
                user_name=mutation.user_name,
                display_name=_parse_display_name_value(value),
                active=mutation.active,
            ),
            enterprise_profile=patch.enterprise_profile,
        )

    return ScimUserPatch(
        user_mutation=UserMutation(
            user_name=mutation.user_name,
            display_name=mutation.display_name,
            active=_parse_active(value),
        ),
        enterprise_profile=patch.enterprise_profile,
    )


def _remove_attribute(
    mutation: UserMutation,
    *,
    path: str,
    current_user: User,
) -> UserMutation:
    if path == "userName":
        _raise_invalid_payload("userName is required and cannot be removed")

    if path == "displayName":
        return UserMutation(
            user_name=mutation.user_name,
            display_name=current_user.email,
            active=mutation.active,
        )

    return UserMutation(
        user_name=mutation.user_name,
        display_name=mutation.display_name,
        active=False,
    )


def _apply_enterprise_attribute_patch(
    patch: ScimUserPatch,
    *,
    op: str,
    path: str,
    value: Any,
) -> ScimUserPatch:
    if path == SCIM_SCHEMA_ENTERPRISE_USER:
        if op == "remove":
            return _merge_enterprise_mutation(patch, _clear_enterprise_mutation())

        if not isinstance(value, dict):
            _raise_invalid_payload("Enterprise User extension value must be an object")

        return _merge_enterprise_mutation(
            patch,
            _parse_enterprise_profile_payload(value),
        )

    if op == "remove":
        parsed_value: str | int | None = None
    elif path == "manager":
        parsed_value = _parse_manager_value(value)
    else:
        parsed_value = _parse_enterprise_string(value, path)

    return _merge_enterprise_mutation(
        patch,
        _enterprise_mutation_for_path(path, parsed_value),
    )


def _normalize_enterprise_patch_path(path: str) -> str | None:
    if path.lower() == SCIM_SCHEMA_ENTERPRISE_USER.lower():
        return SCIM_SCHEMA_ENTERPRISE_USER

    enterprise_prefix = f"{SCIM_SCHEMA_ENTERPRISE_USER}:"
    if path.lower().startswith(enterprise_prefix.lower()):
        path = path[len(enterprise_prefix):]

    return ENTERPRISE_PATCH_PATHS.get(path.lower())


def _merge_enterprise_mutation(
    patch: ScimUserPatch,
    mutation: EnterpriseProfileMutation | None,
) -> ScimUserPatch:
    if mutation is None:
        return patch

    current = patch.enterprise_profile or EnterpriseProfileMutation()
    return ScimUserPatch(
        user_mutation=patch.user_mutation,
        enterprise_profile=EnterpriseProfileMutation(
            employee_number=(
                mutation.employee_number
                if mutation.employee_number is not UNSET
                else current.employee_number
            ),
            department=(
                mutation.department
                if mutation.department is not UNSET
                else current.department
            ),
            division=(
                mutation.division
                if mutation.division is not UNSET
                else current.division
            ),
            organization=(
                mutation.organization
                if mutation.organization is not UNSET
                else current.organization
            ),
            cost_center=(
                mutation.cost_center
                if mutation.cost_center is not UNSET
                else current.cost_center
            ),
            manager_id=(
                mutation.manager_id
                if mutation.manager_id is not UNSET
                else current.manager_id
            ),
        ),
    )


def _enterprise_mutation_for_path(
    path: str,
    value: str | int | None,
) -> EnterpriseProfileMutation:
    if path == "employeeNumber":
        return EnterpriseProfileMutation(employee_number=value)

    if path == "department":
        return EnterpriseProfileMutation(department=value)

    if path == "division":
        return EnterpriseProfileMutation(division=value)

    if path == "organization":
        return EnterpriseProfileMutation(organization=value)

    if path == "costCenter":
        return EnterpriseProfileMutation(cost_center=value)

    if path == "manager":
        return EnterpriseProfileMutation(manager_id=value)

    _raise_invalid_path(f"Unsupported PATCH path: {path}")


def _clear_enterprise_mutation() -> EnterpriseProfileMutation:
    return EnterpriseProfileMutation(
        employee_number=None,
        department=None,
        division=None,
        organization=None,
        cost_center=None,
        manager_id=None,
    )


def _parse_enterprise_profile_payload(
    payload: Any,
) -> EnterpriseProfileMutation | None:
    if payload is UNSET:
        return None

    if not isinstance(payload, dict):
        _raise_invalid_payload("Enterprise User extension must be an object")

    return EnterpriseProfileMutation(
        employee_number=(
            _parse_enterprise_string(payload["employeeNumber"], "employeeNumber")
            if "employeeNumber" in payload
            else UNSET
        ),
        department=(
            _parse_enterprise_string(payload["department"], "department")
            if "department" in payload
            else UNSET
        ),
        division=(
            _parse_enterprise_string(payload["division"], "division")
            if "division" in payload
            else UNSET
        ),
        organization=(
            _parse_enterprise_string(payload["organization"], "organization")
            if "organization" in payload
            else UNSET
        ),
        cost_center=(
            _parse_enterprise_string(payload["costCenter"], "costCenter")
            if "costCenter" in payload
            else UNSET
        ),
        manager_id=(
            _parse_manager_value(payload["manager"])
            if "manager" in payload
            else UNSET
        ),
    )


def _parse_enterprise_string(value: Any, attribute_name: str) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        _raise_invalid_payload(f"{attribute_name} must be a string or null")

    parsed_value = value.strip()
    if not parsed_value:
        _raise_invalid_payload(f"{attribute_name} must not be empty")

    if len(parsed_value) > 100:
        _raise_invalid_payload(f"{attribute_name} must be 100 characters or fewer")

    return parsed_value


def _parse_manager_value(value: Any) -> int | None:
    if value is None:
        return None

    if isinstance(value, dict):
        if "value" not in value:
            _raise_invalid_payload("manager.value is required")

        value = value["value"]

    try:
        manager_id = int(value)
    except (TypeError, ValueError):
        _raise_invalid_payload("manager.value must be a positive user id")

    if manager_id < 1:
        _raise_invalid_payload("manager.value must be a positive user id")

    return manager_id


def _parse_user_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        _raise_invalid_payload("userName is required")

    try:
        return str(EMAIL_ADAPTER.validate_python(value.strip())).lower()
    except ValidationError:
        _raise_invalid_payload("userName must be a valid email address")


def _parse_display_name(payload: dict[str, Any]) -> str:
    display_name = payload.get("displayName")
    if display_name is not None:
        return _parse_display_name_value(display_name)

    name = payload.get("name")
    if isinstance(name, dict) and name.get("formatted") is not None:
        return _parse_display_name_value(name["formatted"])

    _raise_invalid_payload("displayName is required")


def _parse_display_name_value(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        _raise_invalid_payload("displayName must be a non-empty string")

    display_name = value.strip()
    if len(display_name) > 100:
        _raise_invalid_payload("displayName must be 100 characters or fewer")

    return display_name


def _parse_active(value: Any) -> bool:
    if not isinstance(value, bool):
        _raise_invalid_payload("active must be a boolean")

    return value


def _record_provisioning_audit(
    db: Session,
    *,
    actor: User,
    target_user: User,
    action: str,
    result: str,
    reason: str,
    entitlement_slug: str = SCIM_AUDIT_ENTITLEMENT_SLUG,
) -> None:
    entitlement = _get_scim_audit_entitlement(db, entitlement_slug=entitlement_slug)
    create_audit_event(
        db,
        requester_id=actor.id,
        target_user_id=target_user.id,
        action=action,
        application_id=entitlement.application_id,
        entitlement_id=entitlement.id,
        result=result,
        reason=reason,
    )


def _record_enterprise_audits(
    db: Session,
    *,
    actor: User,
    target_user: User,
    changes: list[EnterpriseProfileChange],
) -> None:
    for change in changes:
        action, reason = ENTERPRISE_CHANGE_AUDIT[change.kind]
        _record_provisioning_audit(
            db,
            actor=actor,
            target_user=target_user,
            action=action,
            result="succeeded",
            reason=reason,
            entitlement_slug=SCIM_ENTERPRISE_AUDIT_ENTITLEMENT_SLUG,
        )


def _audit_enterprise_error_and_raise(
    db: Session,
    *,
    actor: User,
    target_user: User | None,
    exc: Exception,
) -> None:
    status_code = status.HTTP_400_BAD_REQUEST
    scim_type = "invalidValue"
    reason = "Enterprise profile validation failed"

    if isinstance(exc, DuplicateEmployeeNumberError):
        status_code = status.HTTP_409_CONFLICT
        scim_type = "uniqueness"
        reason = "Duplicate employeeNumber"
        target_user = exc.existing_profile.user
    elif isinstance(exc, UnknownManagerError):
        reason = "Unknown manager"
    elif isinstance(exc, SelfManagerError):
        reason = "Self manager is not allowed"
    elif isinstance(exc, ManagerCycleError):
        reason = "Manager cycle detected"

    _audit_and_raise(
        db,
        actor=actor,
        target_user=target_user,
        action=ACTION_ENTERPRISE_FAILURE,
        reason=reason,
        status_code=status_code,
        scim_type=scim_type,
        entitlement_slug=SCIM_ENTERPRISE_AUDIT_ENTITLEMENT_SLUG,
    )


def _audit_and_raise(
    db: Session,
    *,
    actor: User,
    target_user: User | None,
    action: str,
    reason: str,
    status_code: int,
    scim_type: str | None = None,
    entitlement_slug: str = SCIM_AUDIT_ENTITLEMENT_SLUG,
) -> None:
    try:
        _record_provisioning_audit(
            db,
            actor=actor,
            target_user=target_user or actor,
            action=action,
            result="denied",
            reason=reason,
            entitlement_slug=entitlement_slug,
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        _raise_database_error(exc)

    raise_scim_error(
        status_code=status_code,
        detail=reason,
        scim_type=scim_type,
    )


def _audit_scim_exception_and_raise(
    db: Session,
    *,
    actor: User,
    target_user: User | None,
    reason: str,
    status_code: int,
    scim_type: str | None,
) -> None:
    _audit_and_raise(
        db,
        actor=actor,
        target_user=target_user,
        action=ACTION_FAILURE,
        reason=reason,
        status_code=status_code,
        scim_type=scim_type,
    )


def _get_scim_audit_entitlement(
    db: Session,
    *,
    entitlement_slug: str,
) -> Entitlement:
    entitlement = db.scalar(
        select(Entitlement)
        .join(Application)
        .where(
            Application.slug == SCIM_AUDIT_APPLICATION_SLUG,
            Entitlement.slug == entitlement_slug,
        )
    )
    if entitlement is None:
        raise RuntimeError("SCIM audit entitlement is not seeded")

    return entitlement


def _successful_update_action(user: User) -> str:
    if user.active:
        return ACTION_UPDATE

    return ACTION_DEACTIVATE


def _successful_update_reason(user: User) -> str:
    if user.active:
        return "User updated"

    return "User deactivated"


def _raise_invalid_payload(detail: str) -> None:
    raise_scim_error(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=detail,
        scim_type="invalidValue",
    )


def _raise_invalid_path(detail: str) -> None:
    raise_scim_error(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=detail,
        scim_type="invalidPath",
    )


def _raise_database_error(exc: Exception) -> None:
    raise_scim_error(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="SCIM provisioning operation failed",
    )
