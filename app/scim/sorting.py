from __future__ import annotations

from fastapi import status
from sqlalchemy import Select, func

from ..models import User
from .errors import raise_scim_error

SUPPORTED_USER_SORT_FIELDS = {
    "id": User.id,
    "userName": func.lower(User.email),
    "displayName": func.lower(User.name),
}
SUPPORTED_SORT_ORDERS = {"ascending", "descending"}


def apply_user_sorting(
    statement: Select[tuple[User]],
    *,
    sort_by: str | None,
    sort_order: str | None,
) -> Select[tuple[User]]:
    normalized_sort_order = sort_order or "ascending"
    if normalized_sort_order not in SUPPORTED_SORT_ORDERS:
        raise_scim_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sortOrder must be ascending or descending",
            scim_type="invalidValue",
        )

    if sort_by is None:
        sort_expression = User.id
    else:
        sort_expression = SUPPORTED_USER_SORT_FIELDS.get(sort_by)
        if sort_expression is None:
            raise_scim_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported sortBy field: {sort_by}",
                scim_type="invalidPath",
            )

    if normalized_sort_order == "descending":
        return statement.order_by(sort_expression.desc(), User.id.desc())

    return statement.order_by(sort_expression.asc(), User.id.asc())
