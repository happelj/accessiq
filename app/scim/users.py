from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import EnterpriseUserProfile, User
from .constants import SCIM_BASE_PATH, SCIM_SCHEMA_ENTERPRISE_USER, SCIM_SCHEMA_USER


def build_user_location(*, base_url: str, user_id: int) -> str:
    return f"{base_url.rstrip('/')}{SCIM_BASE_PATH}/Users/{user_id}"


def user_to_scim_resource(
    user: User,
    *,
    base_url: str,
) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "schemas": [SCIM_SCHEMA_USER],
        "id": str(user.id),
        "userName": user.email,
        "name": {
            "formatted": user.name,
        },
        "displayName": user.name,
        "active": user.active,
        "emails": [
            {
                "value": user.email,
                "type": "work",
                "primary": True,
            }
        ],
        "meta": {
            "resourceType": "User",
            "location": build_user_location(
                base_url=base_url,
                user_id=user.id,
            ),
        },
    }
    enterprise_extension = enterprise_profile_to_scim_extension(
        user.enterprise_profile,
        base_url=base_url,
    )
    if enterprise_extension is not None:
        resource["schemas"] = [SCIM_SCHEMA_USER, SCIM_SCHEMA_ENTERPRISE_USER]
        resource[SCIM_SCHEMA_ENTERPRISE_USER] = enterprise_extension

    return resource


def enterprise_profile_to_scim_extension(
    profile: EnterpriseUserProfile | None,
    *,
    base_url: str,
) -> dict[str, Any] | None:
    if profile is None:
        return None

    extension: dict[str, Any] = {}
    if profile.employee_number is not None:
        extension["employeeNumber"] = profile.employee_number

    if profile.department is not None:
        extension["department"] = profile.department

    if profile.division is not None:
        extension["division"] = profile.division

    if profile.organization is not None:
        extension["organization"] = profile.organization

    if profile.cost_center is not None:
        extension["costCenter"] = profile.cost_center

    if profile.manager_id is not None:
        manager = profile.manager
        manager_resource: dict[str, Any] = {
            "value": str(profile.manager_id),
            "$ref": build_user_location(
                base_url=base_url,
                user_id=profile.manager_id,
            ),
        }
        if manager is not None:
            manager_resource["displayName"] = manager.name

        extension["manager"] = manager_resource

    if not extension:
        return None

    return extension


def get_user_by_scim_id(db: Session, scim_user_id: str) -> User | None:
    try:
        user_id = int(scim_user_id)
    except ValueError:
        return None

    if user_id < 1:
        return None

    return db.get(User, user_id)
