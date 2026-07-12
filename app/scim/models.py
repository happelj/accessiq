from .constants import (
    SCIM_SCHEMA_ENTERPRISE_USER,
    SCIM_SCHEMA_GROUP,
    SCIM_SCHEMA_USER,
)
from .schemas import (
    AuthenticationScheme,
    BulkCapability,
    Capability,
    FilterCapability,
    ResourceType,
    ResourceTypeSchemaExtension,
    SchemaAttribute,
    SchemaResource,
    ServiceProviderConfig,
)


def build_service_provider_config() -> ServiceProviderConfig:
    return ServiceProviderConfig(
        documentationUri="https://github.com/happelj/accessiq#scim-20-groups",
        patch=Capability(supported=True),
        bulk=BulkCapability(supported=False),
        filter=FilterCapability(supported=True, maxResults=100),
        changePassword=Capability(supported=False),
        sort=Capability(supported=True),
        etag=Capability(supported=False),
        xmlDataFormat=Capability(supported=False),
        authenticationSchemes=[
            AuthenticationScheme(
                name="AccessIQ JWT Bearer",
                description=(
                    "SCIM endpoints use the existing AccessIQ JWT bearer "
                    "authentication and API RBAC. Dedicated SCIM bearer tokens "
                    "are planned for a future milestone."
                ),
                type="oauthbearertoken",
                specUri="https://www.rfc-editor.org/rfc/rfc6750",
                primary=True,
            )
        ],
    )


def build_resource_types() -> list[ResourceType]:
    return [
        ResourceType(
            id="User",
            name="User",
            endpoint="/Users",
            description=(
                "User resource type metadata. User read and provisioning "
                "operations are implemented."
            ),
            schema=SCIM_SCHEMA_USER,
            schemaExtensions=[
                ResourceTypeSchemaExtension(
                    schema=SCIM_SCHEMA_ENTERPRISE_USER,
                    required=False,
                )
            ],
        ),
        ResourceType(
            id="Group",
            name="Group",
            endpoint="/Groups",
            description=(
                "Group resource type metadata. Group read and provisioning "
                "operations are implemented."
            ),
            schema=SCIM_SCHEMA_GROUP,
        ),
    ]


def build_user_schema() -> SchemaResource:
    return SchemaResource(
        id=SCIM_SCHEMA_USER,
        name="User",
        description=(
            "Core SCIM User schema metadata. AccessIQ currently supports read "
            "and provisioning operations for User resources."
        ),
        attributes=[
            SchemaAttribute(
                name="userName",
                type="string",
                description="Unique identifier for the User.",
                required=True,
                caseExact=False,
                uniqueness="server",
            ),
            SchemaAttribute(
                name="name",
                type="complex",
                description="The components of the user's real name.",
                subAttributes=[
                    SchemaAttribute(
                        name="formatted",
                        type="string",
                        description="The user's full name.",
                    ),
                    SchemaAttribute(
                        name="givenName",
                        type="string",
                        description="The user's given name.",
                    ),
                    SchemaAttribute(
                        name="familyName",
                        type="string",
                        description="The user's family name.",
                    ),
                ],
            ),
            SchemaAttribute(
                name="displayName",
                type="string",
                description="The name suitable for display to end users.",
            ),
            SchemaAttribute(
                name="active",
                type="boolean",
                description="Whether the user is active.",
            ),
            SchemaAttribute(
                name="emails",
                type="complex",
                multiValued=True,
                description="Email addresses for the user.",
                subAttributes=[
                    SchemaAttribute(
                        name="value",
                        type="string",
                        description="Email address value.",
                    ),
                    SchemaAttribute(
                        name="type",
                        type="string",
                        description="Email address type.",
                        canonicalValues=["work", "home", "other"],
                    ),
                    SchemaAttribute(
                        name="primary",
                        type="boolean",
                        description="Whether this is the primary email address.",
                    ),
                ],
            ),
        ],
    )


def build_group_schema() -> SchemaResource:
    return SchemaResource(
        id=SCIM_SCHEMA_GROUP,
        name="Group",
        description=(
            "Core SCIM Group schema metadata. AccessIQ currently supports read "
            "and provisioning operations for Group resources."
        ),
        attributes=[
            SchemaAttribute(
                name="displayName",
                type="string",
                description="Human-readable name for the group.",
                required=True,
            ),
            SchemaAttribute(
                name="members",
                type="complex",
                multiValued=True,
                description="Users or groups that belong to this group.",
                subAttributes=[
                    SchemaAttribute(
                        name="value",
                        type="string",
                        description="Identifier of the member resource.",
                    ),
                    SchemaAttribute(
                        name="$ref",
                        type="reference",
                        description="URI of the member resource.",
                        referenceTypes=["User", "Group"],
                    ),
                    SchemaAttribute(
                        name="display",
                        type="string",
                        description="Display name of the member resource.",
                    ),
                ],
            ),
        ],
    )


def build_enterprise_user_schema() -> SchemaResource:
    return SchemaResource(
        id=SCIM_SCHEMA_ENTERPRISE_USER,
        name="EnterpriseUser",
        description=(
            "SCIM Enterprise User extension metadata. Enterprise extension "
            "provisioning arrives in a future milestone."
        ),
        attributes=[
            SchemaAttribute(
                name="employeeNumber",
                type="string",
                description="Numeric or alphanumeric identifier assigned to a user.",
            ),
            SchemaAttribute(
                name="costCenter",
                type="string",
                description="Identifies the user's cost center.",
            ),
            SchemaAttribute(
                name="organization",
                type="string",
                description="Identifies the user's organization.",
            ),
            SchemaAttribute(
                name="division",
                type="string",
                description="Identifies the user's division.",
            ),
            SchemaAttribute(
                name="department",
                type="string",
                description="Identifies the user's department.",
            ),
            SchemaAttribute(
                name="manager",
                type="complex",
                description="The user's manager.",
                subAttributes=[
                    SchemaAttribute(
                        name="value",
                        type="string",
                        description="Identifier of the manager resource.",
                    ),
                    SchemaAttribute(
                        name="$ref",
                        type="reference",
                        description="URI of the manager resource.",
                        referenceTypes=["User"],
                    ),
                    SchemaAttribute(
                        name="displayName",
                        type="string",
                        description="Display name of the manager.",
                    ),
                ],
            ),
        ],
    )


def build_schemas() -> list[SchemaResource]:
    return [
        build_user_schema(),
        build_group_schema(),
        build_enterprise_user_schema(),
    ]

