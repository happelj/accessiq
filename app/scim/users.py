from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import User
from .constants import SCIM_BASE_PATH, SCIM_SCHEMA_USER


def build_user_location(*, base_url: str, user_id: int) -> str:
    return f"{base_url.rstrip('/')}{SCIM_BASE_PATH}/Users/{user_id}"


def user_to_scim_resource(
    user: User,
    *,
    base_url: str,
) -> dict[str, Any]:
    return {
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


def get_user_by_scim_id(db: Session, scim_user_id: str) -> User | None:
    try:
        user_id = int(scim_user_id)
    except ValueError:
        return None

    if user_id < 1:
        return None

    return db.get(User, user_id)
