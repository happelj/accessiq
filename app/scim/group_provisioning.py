from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..audit_service import create_audit_event
from ..models import Application, Entitlement, Group, User
from ..services.group_service import (
    DuplicateGroupError,
    DuplicateGroupMemberError,
    GroupNotFoundError,
    GroupPatchOperation,
    GroupService,
    UnknownGroupMemberError,
)
from .errors import ScimHTTPException, raise_scim_error
from .groups import build_group_location, group_to_scim_resource
from .provisioning import SCIM_AUDIT_APPLICATION_SLUG, SCIM_PATCH_SCHEMA

SCIM_GROUP_AUDIT_ENTITLEMENT_SLUG = "group-lifecycle"

ACTION_GROUP_CREATE = "scim_group_create"
ACTION_GROUP_UPDATE = "scim_group_update"
ACTION_GROUP_RENAME = "scim_group_rename"
ACTION_GROUP_MEMBER_ADD = "scim_group_member_add"
ACTION_GROUP_MEMBER_REMOVE = "scim_group_member_remove"
ACTION_GROUP_MEMBERS_REPLACE = "scim_group_members_replace"
ACTION_GROUP_FAILURE = "scim_group_provisioning_failure"

MEMBER_FILTER_PATH_PATTERN = re.compile(
    r'^\s*members\s*\[\s*value\s+eq\s+"(?P<value>[^"]+)"\s*\]\s*$',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ScimGroupPayload:
    display_name: str
    member_ids: tuple[int, ...]


@dataclass(frozen=True)
class ScimGroupProvisioningResult:
    resource: dict[str, Any]
    location: str


def create_scim_group(
    *,
    db: Session,
    actor: User,
    payload: Any,
    base_url: str,
) -> ScimGroupProvisioningResult:
    try:
        group_data = _parse_group_payload(payload)
    except ScimHTTPException as exc:
        _audit_scim_exception_and_raise(
            db,
            actor=actor,
            reason=str(exc.detail),
            status_code=exc.status_code,
            scim_type=exc.scim_type,
        )

    service = GroupService(db)
    try:
        group = service.create_group(
            display_name=group_data.display_name,
            member_ids=group_data.member_ids,
        )
        _record_group_audit(
            db,
            actor=actor,
            action=ACTION_GROUP_CREATE,
            result="succeeded",
            reason="Group created",
        )
        db.commit()
        service.publish_pending_events()
        db.refresh(group)
    except DuplicateGroupError as exc:
        db.rollback()
        _audit_and_raise(
            db,
            actor=actor,
            action=ACTION_GROUP_FAILURE,
            reason="Duplicate displayName",
            status_code=status.HTTP_409_CONFLICT,
            scim_type="uniqueness",
        )
    except DuplicateGroupMemberError as exc:
        db.rollback()
        _audit_and_raise(
            db,
            actor=actor,
            action=ACTION_GROUP_FAILURE,
            reason=f"Duplicate group member {exc.user_id}",
            status_code=status.HTTP_409_CONFLICT,
            scim_type="uniqueness",
        )
    except UnknownGroupMemberError as exc:
        db.rollback()
        _audit_and_raise(
            db,
            actor=actor,
            action=ACTION_GROUP_FAILURE,
            reason=f"Group member {exc.user_id} not found",
            status_code=status.HTTP_400_BAD_REQUEST,
            scim_type="invalidValue",
        )
    except (IntegrityError, SQLAlchemyError) as exc:
        db.rollback()
        _raise_database_error(exc)

    location = build_group_location(base_url=base_url, group_id=group.id)
    return ScimGroupProvisioningResult(
        resource=group_to_scim_resource(group, base_url=base_url),
        location=location,
    )


def replace_scim_group(
    *,
    db: Session,
    actor: User,
    group_id: str,
    payload: Any,
    base_url: str,
) -> ScimGroupProvisioningResult:
    try:
        group_data = _parse_group_payload(payload)
    except ScimHTTPException as exc:
        _audit_scim_exception_and_raise(
            db,
            actor=actor,
            reason=str(exc.detail),
            status_code=exc.status_code,
            scim_type=exc.scim_type,
        )

    service = GroupService(db)
    try:
        group = service.replace_group(
            group_id,
            display_name=group_data.display_name,
            member_ids=group_data.member_ids,
        )
        _record_group_audit(
            db,
            actor=actor,
            action=ACTION_GROUP_UPDATE,
            result="succeeded",
            reason="Group updated",
        )
        db.commit()
        service.publish_pending_events()
        db.refresh(group)
    except (
        DuplicateGroupError,
        DuplicateGroupMemberError,
        GroupNotFoundError,
        UnknownGroupMemberError,
    ) as exc:
        db.rollback()
        _handle_group_service_error(db, actor=actor, exc=exc)
    except (IntegrityError, SQLAlchemyError) as exc:
        db.rollback()
        _raise_database_error(exc)

    return ScimGroupProvisioningResult(
        resource=group_to_scim_resource(group, base_url=base_url),
        location=build_group_location(base_url=base_url, group_id=group.id),
    )


def patch_scim_group(
    *,
    db: Session,
    actor: User,
    group_id: str,
    payload: Any,
    base_url: str,
) -> ScimGroupProvisioningResult:
    service = GroupService(db)
    try:
        operations = _parse_patch_payload(payload)
        audit_action = _audit_action_for_patch(operations)
        audit_reason = _audit_reason_for_patch(operations)
        group = service.patch_group(group_id, operations)
        _record_group_audit(
            db,
            actor=actor,
            action=audit_action,
            result="succeeded",
            reason=audit_reason,
        )
        db.commit()
        service.publish_pending_events()
        db.refresh(group)
    except ScimHTTPException as exc:
        db.rollback()
        _audit_scim_exception_and_raise(
            db,
            actor=actor,
            reason=str(exc.detail),
            status_code=exc.status_code,
            scim_type=exc.scim_type,
        )
    except ValueError as exc:
        db.rollback()
        _audit_and_raise(
            db,
            actor=actor,
            action=ACTION_GROUP_FAILURE,
            reason=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
            scim_type="invalidValue",
        )
    except (
        DuplicateGroupError,
        DuplicateGroupMemberError,
        GroupNotFoundError,
        UnknownGroupMemberError,
    ) as exc:
        db.rollback()
        _handle_group_service_error(db, actor=actor, exc=exc)
    except (IntegrityError, SQLAlchemyError) as exc:
        db.rollback()
        _raise_database_error(exc)

    return ScimGroupProvisioningResult(
        resource=group_to_scim_resource(group, base_url=base_url),
        location=build_group_location(base_url=base_url, group_id=group.id),
    )


def _parse_group_payload(payload: Any) -> ScimGroupPayload:
    if not isinstance(payload, dict):
        _raise_invalid_payload("SCIM Group payload must be a JSON object")

    return ScimGroupPayload(
        display_name=_parse_display_name(payload.get("displayName")),
        member_ids=_parse_member_list(payload.get("members", [])),
    )


def _parse_patch_payload(payload: Any) -> list[GroupPatchOperation]:
    if not isinstance(payload, dict):
        _raise_invalid_payload("SCIM PATCH payload must be a JSON object")

    operations = payload.get("Operations")
    if not isinstance(operations, list) or not operations:
        _raise_invalid_payload("SCIM PATCH requires a non-empty Operations array")

    return [_parse_patch_operation(operation) for operation in operations]


def _parse_patch_operation(operation: Any) -> GroupPatchOperation:
    if not isinstance(operation, dict):
        _raise_invalid_payload("Each PATCH operation must be an object")

    raw_op = operation.get("op")
    if not isinstance(raw_op, str):
        _raise_invalid_payload("Each PATCH operation requires an op")

    op = raw_op.lower()
    if op not in {"add", "remove", "replace"}:
        _raise_invalid_payload(f"Unsupported PATCH operation: {raw_op}")

    raw_path = operation.get("path")
    if raw_path is None:
        if op == "remove":
            _raise_invalid_payload("PATCH remove requires a path")

        value = operation.get("value")
        if not isinstance(value, dict):
            _raise_invalid_payload("PATCH operation without path requires object value")

        if "displayName" in value:
            return GroupPatchOperation(
                op=op,
                path="displayName",
                value=_parse_display_name(value["displayName"]),
            )

        if "members" in value:
            return GroupPatchOperation(
                op=op,
                path="members",
                value=_parse_member_patch_value(value["members"]),
            )

        _raise_invalid_path("PATCH value contains no supported Group attributes")

    if not isinstance(raw_path, str):
        _raise_invalid_path("PATCH path must be a string")

    member_filter_match = MEMBER_FILTER_PATH_PATTERN.match(raw_path)
    if member_filter_match is not None:
        if op != "remove":
            _raise_invalid_path("Filtered members path is supported only for remove")

        return GroupPatchOperation(
            op=op,
            path="members",
            value=(int(member_filter_match.group("value")),),
        )

    normalized_path = raw_path.lower()
    if normalized_path == "displayname":
        if op == "remove":
            _raise_invalid_payload("displayName is required and cannot be removed")
        if "value" not in operation:
            _raise_invalid_payload("PATCH add and replace operations require value")

        return GroupPatchOperation(
            op=op,
            path="displayName",
            value=_parse_display_name(operation.get("value")),
        )

    if normalized_path == "members":
        if op in {"add", "replace"} and "value" not in operation:
            _raise_invalid_payload("PATCH add and replace operations require value")

        return GroupPatchOperation(
            op=op,
            path="members",
            value=_parse_member_patch_value(operation.get("value")),
        )

    _raise_invalid_path(f"Unsupported PATCH path: {raw_path}")


def _parse_display_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        _raise_invalid_payload("displayName is required")

    display_name = value.strip()
    if len(display_name) > 100:
        _raise_invalid_payload("displayName must be 100 characters or fewer")

    return display_name


def _parse_member_patch_value(value: Any) -> tuple[int, ...]:
    if isinstance(value, list):
        return _parse_member_list(value)

    if isinstance(value, dict):
        return (_parse_member_id(value),)

    _raise_invalid_payload("members value must be an object or array")


def _parse_member_list(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list):
        _raise_invalid_payload("members must be an array")

    return tuple(_parse_member_id(member) for member in value)


def _parse_member_id(member: Any) -> int:
    if not isinstance(member, dict):
        _raise_invalid_payload("Each group member must be an object")

    raw_value = member.get("value")
    if not isinstance(raw_value, str) or not raw_value.strip():
        _raise_invalid_payload("Each group member requires a value")

    try:
        member_id = int(raw_value)
    except ValueError:
        _raise_invalid_payload("Group member value must be a user id")

    if member_id < 1:
        _raise_invalid_payload("Group member value must be a positive user id")

    return member_id


def _audit_action_for_patch(
    operations: list[GroupPatchOperation],
) -> str:
    if any(operation.path == "members" and operation.op == "replace" for operation in operations):
        return ACTION_GROUP_MEMBERS_REPLACE

    if any(operation.path == "members" and operation.op == "add" for operation in operations):
        return ACTION_GROUP_MEMBER_ADD

    if any(operation.path == "members" and operation.op == "remove" for operation in operations):
        return ACTION_GROUP_MEMBER_REMOVE

    if any(operation.path == "displayName" for operation in operations):
        return ACTION_GROUP_RENAME

    return ACTION_GROUP_UPDATE


def _audit_reason_for_patch(
    operations: list[GroupPatchOperation],
) -> str:
    action = _audit_action_for_patch(operations)
    return {
        ACTION_GROUP_MEMBERS_REPLACE: "Group members replaced",
        ACTION_GROUP_MEMBER_ADD: "Group member added",
        ACTION_GROUP_MEMBER_REMOVE: "Group member removed",
        ACTION_GROUP_RENAME: "Group renamed",
    }.get(action, "Group updated")


def _record_group_audit(
    db: Session,
    *,
    actor: User,
    action: str,
    result: str,
    reason: str,
) -> None:
    entitlement = _get_group_audit_entitlement(db)
    create_audit_event(
        db,
        requester_id=actor.id,
        target_user_id=actor.id,
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
    action: str,
    reason: str,
    status_code: int,
    scim_type: str | None = None,
) -> None:
    try:
        _record_group_audit(
            db,
            actor=actor,
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
    reason: str,
    status_code: int,
    scim_type: str | None,
) -> None:
    _audit_and_raise(
        db,
        actor=actor,
        action=ACTION_GROUP_FAILURE,
        reason=reason,
        status_code=status_code,
        scim_type=scim_type,
    )


def _handle_group_service_error(
    db: Session,
    *,
    actor: User,
    exc: Exception,
) -> None:
    if isinstance(exc, GroupNotFoundError):
        _audit_and_raise(
            db,
            actor=actor,
            action=ACTION_GROUP_FAILURE,
            reason=f"Group {exc.group_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, DuplicateGroupError):
        _audit_and_raise(
            db,
            actor=actor,
            action=ACTION_GROUP_FAILURE,
            reason="Duplicate displayName",
            status_code=status.HTTP_409_CONFLICT,
            scim_type="uniqueness",
        )

    if isinstance(exc, DuplicateGroupMemberError):
        _audit_and_raise(
            db,
            actor=actor,
            action=ACTION_GROUP_FAILURE,
            reason=f"Duplicate group member {exc.user_id}",
            status_code=status.HTTP_409_CONFLICT,
            scim_type="uniqueness",
        )

    if isinstance(exc, UnknownGroupMemberError):
        _audit_and_raise(
            db,
            actor=actor,
            action=ACTION_GROUP_FAILURE,
            reason=f"Group member {exc.user_id} not found",
            status_code=status.HTTP_400_BAD_REQUEST,
            scim_type="invalidValue",
        )

    _raise_database_error(exc)


def _get_group_audit_entitlement(db: Session) -> Entitlement:
    entitlement = db.scalar(
        select(Entitlement)
        .join(Application)
        .where(
            Application.slug == SCIM_AUDIT_APPLICATION_SLUG,
            Entitlement.slug == SCIM_GROUP_AUDIT_ENTITLEMENT_SLUG,
        )
    )
    if entitlement is None:
        raise RuntimeError("SCIM group audit entitlement is not seeded")

    return entitlement


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
        detail="SCIM group provisioning operation failed",
    )
