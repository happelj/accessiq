from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from .auth import get_current_user
from .models import User
from .roles import validate_operator_role


def forbidden_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient privileges",
    )


def require_roles(*roles: str) -> Callable[[User], User]:
    allowed_roles = frozenset(validate_operator_role(role) for role in roles)

    if not allowed_roles:
        raise ValueError("At least one role is required")

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        try:
            current_role = validate_operator_role(current_user.operator_role)
        except ValueError as exc:
            raise forbidden_exception() from exc

        if current_role not in allowed_roles:
            raise forbidden_exception()

        return current_user

    return dependency
