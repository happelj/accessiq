from dataclasses import dataclass
from typing import Any

from fastapi import status
from pydantic import BaseModel, Field

from .constants import SCIM_SCHEMA_LIST_RESPONSE
from .errors import raise_scim_error

DEFAULT_SCIM_COUNT = 100


class ScimListResponse(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [SCIM_SCHEMA_LIST_RESPONSE])
    totalResults: int = Field(ge=0)
    startIndex: int = Field(default=1, ge=1)
    itemsPerPage: int = Field(default=0, ge=0)
    Resources: list[Any] = Field(default_factory=list)


@dataclass(frozen=True)
class ScimPagination:
    start_index: int = 1
    count: int = DEFAULT_SCIM_COUNT

    @property
    def offset(self) -> int:
        return self.start_index - 1


def _parse_integer_query_parameter(
    *,
    name: str,
    value: str | None,
    default: int,
    minimum: int,
) -> int:
    if value is None:
        return default

    try:
        parsed_value = int(value)
    except ValueError:
        raise_scim_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{name} must be an integer",
            scim_type="invalidValue",
        )

    if parsed_value < minimum:
        raise_scim_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{name} must be greater than or equal to {minimum}",
            scim_type="invalidValue",
        )

    return parsed_value


def parse_pagination_parameters(
    *,
    start_index: str | None,
    count: str | None,
) -> ScimPagination:
    return ScimPagination(
        start_index=_parse_integer_query_parameter(
            name="startIndex",
            value=start_index,
            default=1,
            minimum=1,
        ),
        count=_parse_integer_query_parameter(
            name="count",
            value=count,
            default=DEFAULT_SCIM_COUNT,
            minimum=0,
        ),
    )

