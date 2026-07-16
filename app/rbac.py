from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from .auth import get_current_user
from .models import User
from .observability import log_event, record_rbac_denial
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
            record_rbac_denial(
                role=current_user.operator_role,
                required_roles=sorted(allowed_roles),
            )
            log_event(
                "rbac_denial",
                status="denied",
                role=current_user.operator_role,
                required_roles=sorted(allowed_roles),
                reason="invalid_operator_role",
            )
            raise forbidden_exception() from exc

        if current_role not in allowed_roles:
            record_rbac_denial(
                role=current_role,
                required_roles=sorted(allowed_roles),
            )
            log_event(
                "rbac_denial",
                status="denied",
                role=current_role,
                required_roles=sorted(allowed_roles),
                reason="insufficient_privileges",
            )
            raise forbidden_exception()

        return current_user

    return dependency
