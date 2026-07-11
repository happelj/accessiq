from __future__ import annotations

from fastapi import status
from sqlalchemy import Select, func
from sqlalchemy.sql.elements import ColumnElement

from ..models import Group, User
from .errors import raise_scim_error

SUPPORTED_USER_SORT_FIELDS = {
    "id": User.id,
    "userName": func.lower(User.email),
    "displayName": func.lower(User.name),
}
SUPPORTED_GROUP_SORT_FIELDS = {
    "id": Group.id,
    "displayName": func.lower(Group.display_name),
}
SUPPORTED_SORT_ORDERS = {"ascending", "descending"}


def apply_scim_sorting(
    statement: Select,
    *,
    sort_by: str | None,
    sort_order: str | None,
    supported_sort_fields: dict[str, ColumnElement],
    default_sort_field: ColumnElement,
    tie_breaker: ColumnElement,
) -> Select:
    normalized_sort_order = sort_order or "ascending"
    if normalized_sort_order not in SUPPORTED_SORT_ORDERS:
        raise_scim_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sortOrder must be ascending or descending",
            scim_type="invalidValue",
        )

    if sort_by is None:
        sort_expression = default_sort_field
    else:
        sort_expression = supported_sort_fields.get(sort_by)
        if sort_expression is None:
            raise_scim_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported sortBy field: {sort_by}",
                scim_type="invalidPath",
            )

    if normalized_sort_order == "descending":
        return statement.order_by(sort_expression.desc(), tie_breaker.desc())

    return statement.order_by(sort_expression.asc(), tie_breaker.asc())


def apply_user_sorting(
    statement: Select[tuple[User]],
    *,
    sort_by: str | None,
    sort_order: str | None,
) -> Select[tuple[User]]:
    return apply_scim_sorting(
        statement,
        sort_by=sort_by,
        sort_order=sort_order,
        supported_sort_fields=SUPPORTED_USER_SORT_FIELDS,
        default_sort_field=User.id,
        tie_breaker=User.id,
    )


def apply_group_sorting(
    statement: Select[tuple[Group]],
    *,
    sort_by: str | None,
    sort_order: str | None,
) -> Select[tuple[Group]]:
    return apply_scim_sorting(
        statement,
        sort_by=sort_by,
        sort_order=sort_order,
        supported_sort_fields=SUPPORTED_GROUP_SORT_FIELDS,
        default_sort_field=Group.id,
        tie_breaker=Group.id,
    )
