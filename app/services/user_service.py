from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import hash_password
from ..models import User

DEFAULT_PROVISIONED_DEPARTMENT = "SCIM Provisioned"
DEFAULT_PROVISIONED_OPERATOR_ROLE = "employee"


@dataclass(frozen=True)
class UserMutation:
    user_name: str | None = None
    display_name: str | None = None
    active: bool | None = None


class UserServiceError(Exception):
    """Base exception for reusable user service failures."""


class DuplicateUserNameError(UserServiceError):
    def __init__(self, user_name: str, existing_user: User) -> None:
        super().__init__(f"User with userName {user_name!r} already exists")
        self.user_name = user_name
        self.existing_user = existing_user


class UserNotFoundError(UserServiceError):
    def __init__(self, user_id: str) -> None:
        super().__init__(f"User {user_id!r} was not found")
        self.user_id = user_id


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_user(self, user_id: str) -> User | None:
        try:
            parsed_user_id = int(user_id)
        except ValueError:
            return None

        if parsed_user_id < 1:
            return None

        return self.db.get(User, parsed_user_id)

    def find_user_by_user_name(self, user_name: str) -> User | None:
        return self.db.scalar(
            select(User).where(func.lower(User.email) == user_name.lower())
        )

    def create_user(
        self,
        *,
        user_name: str,
        display_name: str,
        active: bool,
    ) -> User:
        existing_user = self.find_user_by_user_name(user_name)
        if existing_user is not None:
            raise DuplicateUserNameError(user_name, existing_user)

        user = User(
            name=display_name,
            email=user_name.lower(),
            department=DEFAULT_PROVISIONED_DEPARTMENT,
            active=active,
            operator_role=DEFAULT_PROVISIONED_OPERATOR_ROLE,
            password_hash=hash_password(f"scim-{uuid4()}"),
        )

        self.db.add(user)
        self.db.flush()

        return user

    def replace_user(
        self,
        user_id: str,
        *,
        user_name: str,
        display_name: str,
        active: bool,
    ) -> User:
        user = self._require_user(user_id)
        self._ensure_user_name_available(user_name, current_user=user)

        user.email = user_name.lower()
        user.name = display_name
        user.active = active
        self.db.flush()

        return user

    def patch_user(
        self,
        user_id: str,
        mutation: UserMutation,
    ) -> User:
        user = self._require_user(user_id)

        if mutation.user_name is not None:
            self._ensure_user_name_available(
                mutation.user_name,
                current_user=user,
            )
            user.email = mutation.user_name.lower()

        if mutation.display_name is not None:
            user.name = mutation.display_name

        if mutation.active is not None:
            user.active = mutation.active

        self.db.flush()

        return user

    def deactivate_user(self, user_id: str) -> User:
        user = self._require_user(user_id)
        user.active = False
        self.db.flush()

        return user

    def _require_user(self, user_id: str) -> User:
        user = self.find_user(user_id)
        if user is None:
            raise UserNotFoundError(user_id)

        return user

    def _ensure_user_name_available(
        self,
        user_name: str,
        *,
        current_user: User | None = None,
    ) -> None:
        existing_user = self.find_user_by_user_name(user_name)
        if existing_user is None:
            return

        if current_user is not None and existing_user.id == current_user.id:
            return

        raise DuplicateUserNameError(user_name, existing_user)
