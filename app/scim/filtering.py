from __future__ import annotations

import json
import re
from dataclasses import dataclass

from fastapi import status
from sqlalchemy import false, func
from sqlalchemy.sql.elements import ColumnElement

from ..models import User
from .errors import raise_scim_error

FILTER_PATTERN = re.compile(
    r'^\s*(?P<attribute>[A-Za-z][A-Za-z0-9_.:-]*)\s+'
    r'(?P<operator>[A-Za-z]+)\s+'
    r'(?P<value>.+?)\s*$'
)


@dataclass(frozen=True)
class ScimFilter:
    attribute: str
    operator: str
    value: str | bool


def parse_scim_filter(filter_value: str | None) -> ScimFilter | None:
    if filter_value is None:
        return None

    match = FILTER_PATTERN.match(filter_value)
    if match is None:
        _raise_invalid_filter("Malformed SCIM filter")

    attribute = match.group("attribute")
    operator = match.group("operator").lower()
    raw_value = match.group("value")

    if attribute == "active":
        if operator != "eq":
            _raise_invalid_filter("active supports only the eq operator")

        lowered_value = raw_value.lower()
        if lowered_value not in {"true", "false"}:
            _raise_invalid_filter("active filters must compare to true or false")

        return ScimFilter(
            attribute=attribute,
            operator=operator,
            value=lowered_value == "true",
        )

    supported_string_filters = {
        "userName": {"eq"},
        "id": {"eq"},
        "displayName": {"co"},
    }
    supported_operators = supported_string_filters.get(attribute)
    if supported_operators is None:
        _raise_invalid_filter(f"Unsupported filter attribute: {attribute}")

    if operator not in supported_operators:
        _raise_invalid_filter(
            f"{attribute} does not support the {operator} operator"
        )

    return ScimFilter(
        attribute=attribute,
        operator=operator,
        value=_parse_quoted_string(raw_value),
    )


def build_user_filter_expression(
    filter_: ScimFilter | None,
) -> ColumnElement[bool] | None:
    if filter_ is None:
        return None

    if filter_.attribute == "userName":
        return func.lower(User.email) == str(filter_.value).lower()

    if filter_.attribute == "id":
        try:
            user_id = int(str(filter_.value))
        except ValueError:
            return false()

        return User.id == user_id

    if filter_.attribute == "displayName":
        return User.name.ilike(
            f"%{_escape_like_pattern(str(filter_.value))}%",
            escape="\\",
        )

    if filter_.attribute == "active":
        return User.active.is_(filter_.value)

    _raise_invalid_filter(f"Unsupported filter attribute: {filter_.attribute}")


def _parse_quoted_string(raw_value: str) -> str:
    try:
        parsed_value = json.loads(raw_value)
    except json.JSONDecodeError:
        _raise_invalid_filter("String filter values must be quoted")

    if not isinstance(parsed_value, str):
        _raise_invalid_filter("String filter values must be quoted")

    return parsed_value


def _escape_like_pattern(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _raise_invalid_filter(detail: str) -> None:
    raise_scim_error(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=detail,
        scim_type="invalidFilter",
    )
