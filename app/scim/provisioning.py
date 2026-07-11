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
from ..services.user_service import (
    DuplicateUserNameError,
    UserMutation,
    UserNotFoundError,
    UserService,
)
from .constants import SCIM_SCHEMA_USER
from .errors import ScimHTTPException, raise_scim_error
from .users import build_user_location, user_to_scim_resource

SCIM_PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
SCIM_AUDIT_APPLICATION_SLUG = "scim-provisioning"
SCIM_AUDIT_ENTITLEMENT_SLUG = "user-lifecycle"

ACTION_CREATE = "scim_user_create"
ACTION_UPDATE = "scim_user_update"
ACTION_DEACTIVATE = "scim_user_deactivate"
ACTION_FAILURE = "scim_user_provisioning_failure"

EMAIL_ADAPTER = TypeAdapter(EmailStr)
PATCH_PATHS = {
    "username": "userName",
    "displayname": "displayName",
    "active": "active",
}


@dataclass(frozen=True)
class ScimUserPayload:
    user_name: str
    display_name: str
    active: bool


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

    try:
        user = service.create_user(
            user_name=user_data.user_name,
            display_name=user_data.display_name,
            active=user_data.active,
        )
        _record_provisioning_audit(
            db,
            actor=actor,
            target_user=user,
            action=ACTION_CREATE,
            result="succeeded",
            reason="User created",
        )
        db.commit()
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

    try:
        user = service.replace_user(
            user_id,
            user_name=user_data.user_name,
            display_name=user_data.display_name,
            active=user_data.active,
        )
        _record_provisioning_audit(
            db,
            actor=actor,
            target_user=user,
            action=_successful_update_action(user),
            result="succeeded",
            reason=_successful_update_reason(user),
        )
        db.commit()
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

    try:
        current_user = service.find_user(user_id)
        if current_user is None:
            raise UserNotFoundError(user_id)

        try:
            mutation = _parse_patch_payload(payload, current_user=current_user)
        except ScimHTTPException as exc:
            _audit_scim_exception_and_raise(
                db,
                actor=actor,
                target_user=current_user,
                reason=str(exc.detail),
                status_code=exc.status_code,
                scim_type=exc.scim_type,
            )

        user = service.patch_user(user_id, mutation)
        _record_provisioning_audit(
            db,
            actor=actor,
            target_user=user,
            action=_successful_update_action(user),
            result="succeeded",
            reason=_successful_update_reason(user),
        )
        db.commit()
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

    return ScimUserPayload(
        user_name=user_name,
        display_name=display_name,
        active=active,
    )


def _parse_patch_payload(
    payload: Any,
    *,
    current_user: User,
) -> UserMutation:
    if not isinstance(payload, dict):
        _raise_invalid_payload("SCIM PATCH payload must be a JSON object")

    operations = payload.get("Operations")
    if not isinstance(operations, list) or not operations:
        _raise_invalid_payload("SCIM PATCH requires a non-empty Operations array")

    mutation = UserMutation()
    for operation in operations:
        mutation = _apply_patch_operation(
            mutation,
            operation=operation,
            current_user=current_user,
        )

    return mutation


def _apply_patch_operation(
    mutation: UserMutation,
    *,
    operation: Any,
    current_user: User,
) -> UserMutation:
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
            mutation = _apply_attribute_patch(
                mutation,
                op=op,
                path=str(attribute),
                value=attribute_value,
                current_user=current_user,
            )

        return mutation

    if not isinstance(raw_path, str):
        _raise_invalid_path("PATCH path must be a string")

    value = operation.get("value")
    if op in {"add", "replace"} and "value" not in operation:
        _raise_invalid_payload("PATCH add and replace operations require value")

    return _apply_attribute_patch(
        mutation,
        op=op,
        path=raw_path,
        value=value,
        current_user=current_user,
    )


def _apply_attribute_patch(
    mutation: UserMutation,
    *,
    op: str,
    path: str,
    value: Any,
    current_user: User,
) -> UserMutation:
    normalized_path = PATCH_PATHS.get(path.lower())
    if normalized_path is None:
        _raise_invalid_path(f"Unsupported PATCH path: {path}")

    if op == "remove":
        return _remove_attribute(
            mutation,
            path=normalized_path,
            current_user=current_user,
        )

    if normalized_path == "userName":
        return UserMutation(
            user_name=_parse_user_name(value),
            display_name=mutation.display_name,
            active=mutation.active,
        )

    if normalized_path == "displayName":
        return UserMutation(
            user_name=mutation.user_name,
            display_name=_parse_display_name_value(value),
            active=mutation.active,
        )

    return UserMutation(
        user_name=mutation.user_name,
        display_name=mutation.display_name,
        active=_parse_active(value),
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
) -> None:
    entitlement = _get_scim_audit_entitlement(db)
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


def _audit_and_raise(
    db: Session,
    *,
    actor: User,
    target_user: User | None,
    action: str,
    reason: str,
    status_code: int,
    scim_type: str | None = None,
) -> None:
    try:
        _record_provisioning_audit(
            db,
            actor=actor,
            target_user=target_user or actor,
            action=action,
            result="denied",
            reason=reason,
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


def _get_scim_audit_entitlement(db: Session) -> Entitlement:
    entitlement = db.scalar(
        select(Entitlement)
        .join(Application)
        .where(
            Application.slug == SCIM_AUDIT_APPLICATION_SLUG,
            Entitlement.slug == SCIM_AUDIT_ENTITLEMENT_SLUG,
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
