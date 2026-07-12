from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import Group
from .constants import SCIM_BASE_PATH, SCIM_SCHEMA_GROUP


def build_group_location(*, base_url: str, group_id: int) -> str:
    return f"{base_url.rstrip('/')}{SCIM_BASE_PATH}/Groups/{group_id}"


def build_group_member_location(*, base_url: str, user_id: int) -> str:
    return f"{base_url.rstrip('/')}{SCIM_BASE_PATH}/Users/{user_id}"


def group_to_scim_resource(
    group: Group,
    *,
    base_url: str,
) -> dict[str, Any]:
    members = [
        {
            "value": str(membership.user.id),
            "$ref": build_group_member_location(
                base_url=base_url,
                user_id=membership.user.id,
            ),
            "display": membership.user.name,
        }
        for membership in sorted(
            group.memberships,
            key=lambda membership: membership.user_id,
        )
    ]

    return {
        "schemas": [SCIM_SCHEMA_GROUP],
        "id": str(group.id),
        "displayName": group.display_name,
        "members": members,
        "meta": {
            "resourceType": "Group",
            "location": build_group_location(
                base_url=base_url,
                group_id=group.id,
            ),
            "lastModified": group.updated_at.isoformat(),
        },
    }


def get_group_by_scim_id(db: Session, scim_group_id: str) -> Group | None:
    try:
        group_id = int(scim_group_id)
    except ValueError:
        return None

    if group_id < 1:
        return None

    return db.get(Group, group_id)
