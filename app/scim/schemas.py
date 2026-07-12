from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .constants import (
    SCIM_SCHEMA_ERROR,
    SCIM_SCHEMA_GROUP,
    SCIM_SCHEMA_RESOURCE_TYPE,
    SCIM_SCHEMA_SCHEMA,
    SCIM_SCHEMA_SERVICE_PROVIDER_CONFIG,
    SCIM_SCHEMA_USER,
)


class ScimErrorResponse(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [SCIM_SCHEMA_ERROR])
    detail: str
    status: str
    scimType: str | None = None


class Capability(BaseModel):
    supported: bool


class BulkCapability(Capability):
    maxOperations: int = 0
    maxPayloadSize: int = 0


class FilterCapability(Capability):
    maxResults: int = 0


class AuthenticationScheme(BaseModel):
    name: str
    description: str
    type: str
    specUri: str | None = None
    documentationUri: str | None = None
    primary: bool = False


class ServiceProviderConfig(BaseModel):
    schemas: list[str] = Field(
        default_factory=lambda: [SCIM_SCHEMA_SERVICE_PROVIDER_CONFIG],
    )
    documentationUri: str
    patch: Capability
    bulk: BulkCapability
    filter: FilterCapability
    changePassword: Capability
    sort: Capability
    etag: Capability
    xmlDataFormat: Capability
    authenticationSchemes: list[AuthenticationScheme]


class ResourceTypeSchemaExtension(BaseModel):
    schema_: str = Field(alias="schema")
    required: bool

    model_config = ConfigDict(populate_by_name=True)


class ResourceType(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [SCIM_SCHEMA_RESOURCE_TYPE])
    id: str
    name: str
    endpoint: str
    description: str
    schema_: str = Field(alias="schema")
    schemaExtensions: list[ResourceTypeSchemaExtension] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class SchemaAttribute(BaseModel):
    name: str
    type: Literal[
        "string",
        "boolean",
        "decimal",
        "integer",
        "dateTime",
        "reference",
        "complex",
        "binary",
    ]
    multiValued: bool = False
    description: str
    required: bool = False
    caseExact: bool = False
    mutability: Literal["readOnly", "readWrite", "immutable", "writeOnly"] = (
        "readWrite"
    )
    returned: Literal["always", "never", "default", "request"] = "default"
    uniqueness: Literal["none", "server", "global"] = "none"
    canonicalValues: list[str] | None = None
    referenceTypes: list[str] | None = None
    subAttributes: list["SchemaAttribute"] = Field(default_factory=list)


class SchemaResource(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [SCIM_SCHEMA_SCHEMA])
    id: str
    name: str
    description: str
    attributes: list[SchemaAttribute]


class ScimName(BaseModel):
    formatted: str | None = None
    givenName: str | None = None
    familyName: str | None = None


class ScimEmail(BaseModel):
    value: str
    type: str = "work"
    primary: bool = True


class ScimMeta(BaseModel):
    resourceType: str
    location: str | None = None
    lastModified: datetime | None = None


class ScimUserResource(BaseModel):
    model_config = ConfigDict(extra="allow")

    schemas: list[str] = Field(default_factory=lambda: [SCIM_SCHEMA_USER])
    id: str
    userName: str | None = None
    name: ScimName | None = None
    displayName: str | None = None
    active: bool | None = None
    emails: list[ScimEmail] | None = None
    meta: ScimMeta | None = None


class ScimGroupMember(BaseModel):
    value: str
    ref: str | None = Field(default=None, alias="$ref")
    display: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class ScimGroupResource(BaseModel):
    model_config = ConfigDict(extra="allow")

    schemas: list[str] = Field(default_factory=lambda: [SCIM_SCHEMA_GROUP])
    id: str
    displayName: str | None = None
    members: list[ScimGroupMember] | None = None
    meta: ScimMeta | None = None


ScimResource = dict[str, Any]

