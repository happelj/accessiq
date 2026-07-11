from typing import Any

from pydantic import BaseModel, Field

from .constants import SCIM_SCHEMA_LIST_RESPONSE


class ScimListResponse(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [SCIM_SCHEMA_LIST_RESPONSE])
    totalResults: int = Field(ge=0)
    startIndex: int = Field(default=1, ge=1)
    itemsPerPage: int = Field(default=0, ge=0)
    Resources: list[Any] = Field(default_factory=list)

