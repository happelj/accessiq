from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..rbac import require_roles
from .constants import SCIM_BASE_PATH, SCIM_MEDIA_TYPE, SCIM_SCHEMA_USER
from .errors import SCIM_ERROR_RESPONSES, raise_scim_error
from .filtering import build_user_filter_expression, parse_scim_filter
from .models import (
    build_resource_types,
    build_schemas,
    build_service_provider_config,
)
from .pagination import ScimListResponse, parse_pagination_parameters
from .projection import apply_attribute_projection, parse_attribute_projection
from .provisioning import (
    SCIM_PATCH_SCHEMA,
    create_scim_user,
    patch_scim_user,
    replace_scim_user,
)
from .schemas import ScimUserResource, ServiceProviderConfig
from .sorting import apply_user_sorting
from .users import get_user_by_scim_id, user_to_scim_resource


class SCIMJSONResponse(JSONResponse):
    media_type = SCIM_MEDIA_TYPE


require_scim_admin = require_roles("security_admin", "iam_admin")

SCIM_USER_EXAMPLE = {
    "schemas": [SCIM_SCHEMA_USER],
    "id": "1",
    "userName": "alice@example.com",
    "name": {"formatted": "Alice Johnson"},
    "displayName": "Alice Johnson",
    "active": True,
    "emails": [
        {
            "value": "alice@example.com",
            "type": "work",
            "primary": True,
        }
    ],
    "meta": {
        "resourceType": "User",
        "location": "https://accessiq.example.com/scim/v2/Users/1",
    },
}
SCIM_USER_LIST_RESPONSES = {
    **SCIM_ERROR_RESPONSES,
    200: {
        "description": "SCIM ListResponse containing User resources",
        "content": {
            SCIM_MEDIA_TYPE: {
                "example": {
                    "schemas": [
                        "urn:ietf:params:scim:api:messages:2.0:ListResponse"
                    ],
                    "totalResults": 1,
                    "startIndex": 1,
                    "itemsPerPage": 1,
                    "Resources": [SCIM_USER_EXAMPLE],
                }
            }
        },
    },
}
SCIM_USER_RESPONSES = {
    **SCIM_ERROR_RESPONSES,
    200: {
        "description": "SCIM User resource",
        "content": {
            SCIM_MEDIA_TYPE: {
                "example": SCIM_USER_EXAMPLE,
            }
        },
    },
}
SCIM_USER_CREATED_RESPONSES = {
    **SCIM_ERROR_RESPONSES,
    201: {
        "description": "Created SCIM User resource",
        "headers": {
            "Location": {
                "description": "Canonical SCIM URL for the created User.",
                "schema": {"type": "string"},
            }
        },
        "content": {
            SCIM_MEDIA_TYPE: {
                "example": SCIM_USER_EXAMPLE,
            }
        },
    },
}
SCIM_USER_REQUEST_EXAMPLE = {
    "schemas": [SCIM_SCHEMA_USER],
    "userName": "new.user@example.com",
    "displayName": "New User",
    "active": True,
}
SCIM_PATCH_REQUEST_EXAMPLE = {
    "schemas": [SCIM_PATCH_SCHEMA],
    "Operations": [
        {
            "op": "replace",
            "path": "active",
            "value": False,
        }
    ],
}
SCIM_USER_REQUEST_BODY = {
    "content": {
        SCIM_MEDIA_TYPE: {
            "examples": {
                "create-active-user": {
                    "summary": "Create an active user",
                    "value": SCIM_USER_REQUEST_EXAMPLE,
                },
                "deactivate-by-replacement": {
                    "summary": "Set active false through replacement",
                    "value": {
                        **SCIM_USER_REQUEST_EXAMPLE,
                        "active": False,
                    },
                },
            }
        }
    },
    "required": True,
}
SCIM_PATCH_REQUEST_BODY = {
    "content": {
        SCIM_MEDIA_TYPE: {
            "examples": {
                "replace-active": {
                    "summary": "Deactivate a user",
                    "value": SCIM_PATCH_REQUEST_EXAMPLE,
                },
                "replace-display-name": {
                    "summary": "Update displayName",
                    "value": {
                        "schemas": [SCIM_PATCH_SCHEMA],
                        "Operations": [
                            {
                                "op": "replace",
                                "path": "displayName",
                                "value": "Updated User",
                            }
                        ],
                    },
                },
                "add-user-name": {
                    "summary": "Update userName",
                    "value": {
                        "schemas": [SCIM_PATCH_SCHEMA],
                        "Operations": [
                            {
                                "op": "add",
                                "path": "userName",
                                "value": "updated.user@example.com",
                            }
                        ],
                    },
                },
            }
        }
    },
    "required": True,
}

router = APIRouter(
    prefix=SCIM_BASE_PATH,
    tags=["SCIM"],
    dependencies=[Depends(require_scim_admin)],
)


@router.get(
    "/ServiceProviderConfig",
    response_model=ServiceProviderConfig,
    response_class=SCIMJSONResponse,
    responses=SCIM_ERROR_RESPONSES,
    status_code=status.HTTP_200_OK,
    summary="Get SCIM service provider configuration",
    description=(
        "Returns AccessIQ's SCIM 2.0 ServiceProviderConfig metadata. "
        "User read operations are implemented; provisioning endpoints are "
        "planned for Milestone 6C."
    ),
)
def get_service_provider_config() -> ServiceProviderConfig:
    return build_service_provider_config()


@router.get(
    "/ResourceTypes",
    response_model=ScimListResponse,
    response_class=SCIMJSONResponse,
    responses=SCIM_ERROR_RESPONSES,
    status_code=status.HTTP_200_OK,
    summary="List SCIM resource types",
    description=(
        "Returns SCIM ResourceType metadata for User and Group resources. "
        "The actual provisioning endpoints are intentionally not implemented "
        "in this milestone."
    ),
)
def list_resource_types() -> ScimListResponse:
    resource_types = build_resource_types()
    resources = [
        resource_type.model_dump(by_alias=True, exclude_none=True)
        for resource_type in resource_types
    ]
    return ScimListResponse(
        totalResults=len(resources),
        itemsPerPage=len(resources),
        Resources=resources,
    )


@router.get(
    "/Users",
    response_model=ScimListResponse,
    response_class=SCIMJSONResponse,
    responses=SCIM_USER_LIST_RESPONSES,
    status_code=status.HTTP_200_OK,
    summary="List SCIM users",
    description=(
        "Returns AccessIQ users as SCIM 2.0 User resources. Supports "
        "1-based pagination (`startIndex`, `count`), a practical filter "
        "subset (`userName eq`, `id eq`, `displayName co`, `active eq`), "
        "attribute projection (`attributes`, `excludedAttributes`), and "
        "sorting by `id`, `userName`, or `displayName`."
    ),
)
def list_users(
    request: Request,
    start_index: str | None = Query(
        default="1",
        alias="startIndex",
        description="1-based index of the first result to return.",
    ),
    count: str | None = Query(
        default="100",
        description="Maximum number of User resources to return.",
    ),
    filter_: str | None = Query(
        default=None,
        alias="filter",
        description=(
            'Supported filters: `userName eq "alice@example.com"`, '
            '`id eq "123"`, `displayName co "Alice"`, '
            "`active eq true`, and `active eq false`."
        ),
    ),
    attributes: str | None = Query(
        default=None,
        description="Comma-separated top-level SCIM attributes to include.",
    ),
    excluded_attributes: str | None = Query(
        default=None,
        alias="excludedAttributes",
        description="Comma-separated top-level SCIM attributes to omit.",
    ),
    sort_by: str | None = Query(
        default=None,
        alias="sortBy",
        description="Optional sort field: `id`, `userName`, or `displayName`.",
    ),
    sort_order: str | None = Query(
        default=None,
        alias="sortOrder",
        description="Optional sort order: `ascending` or `descending`.",
    ),
    db: Session = Depends(get_db),
) -> ScimListResponse:
    pagination = parse_pagination_parameters(
        start_index=start_index,
        count=count,
    )
    scim_filter = parse_scim_filter(filter_)
    filter_expression = build_user_filter_expression(scim_filter)
    projection = parse_attribute_projection(
        attributes=attributes,
        excluded_attributes=excluded_attributes,
    )

    count_statement = select(func.count(User.id))
    user_statement = select(User)
    if filter_expression is not None:
        count_statement = count_statement.where(filter_expression)
        user_statement = user_statement.where(filter_expression)

    total_results = db.scalar(count_statement) or 0
    user_statement = apply_user_sorting(
        user_statement,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    users = db.scalars(
        user_statement.offset(pagination.offset).limit(pagination.count)
    ).all()
    resources = [
        apply_attribute_projection(
            user_to_scim_resource(
                user,
                base_url=str(request.base_url),
            ),
            projection,
        )
        for user in users
    ]

    return ScimListResponse(
        totalResults=total_results,
        startIndex=pagination.start_index,
        itemsPerPage=len(resources),
        Resources=resources,
    )


@router.post(
    "/Users",
    response_model=ScimUserResource,
    response_class=SCIMJSONResponse,
    responses=SCIM_USER_CREATED_RESPONSES,
    status_code=status.HTTP_201_CREATED,
    summary="Create a SCIM user",
    description=(
        "Creates an AccessIQ user from a SCIM 2.0 User payload. "
        "`userName` maps to the AccessIQ email, `displayName` maps to the "
        "AccessIQ display name, and `active` controls the active flag. "
        "Provisioned users are assigned the default employee operator role."
    ),
    openapi_extra={"requestBody": SCIM_USER_REQUEST_BODY},
)
def create_user(
    request: Request,
    payload: Any = Body(default=None, media_type=SCIM_MEDIA_TYPE),
    current_user: User = Depends(require_scim_admin),
    db: Session = Depends(get_db),
) -> SCIMJSONResponse:
    result = create_scim_user(
        db=db,
        actor=current_user,
        payload=payload,
        base_url=str(request.base_url),
    )

    return SCIMJSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=result.resource,
        headers={"Location": result.location},
    )


@router.get(
    "/Users/{user_id}",
    response_model=ScimUserResource,
    response_model_exclude_none=True,
    response_class=SCIMJSONResponse,
    responses=SCIM_USER_RESPONSES,
    status_code=status.HTTP_200_OK,
    summary="Get a SCIM user",
    description=(
        "Returns one AccessIQ user as a SCIM 2.0 User resource by SCIM id. "
        "Supports `attributes` and `excludedAttributes` projection."
    ),
)
def get_user(
    user_id: str,
    request: Request,
    attributes: str | None = Query(
        default=None,
        description="Comma-separated top-level SCIM attributes to include.",
    ),
    excluded_attributes: str | None = Query(
        default=None,
        alias="excludedAttributes",
        description="Comma-separated top-level SCIM attributes to omit.",
    ),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    user = get_user_by_scim_id(db, user_id)
    if user is None:
        raise_scim_error(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    projection = parse_attribute_projection(
        attributes=attributes,
        excluded_attributes=excluded_attributes,
    )
    return apply_attribute_projection(
        user_to_scim_resource(
            user,
            base_url=str(request.base_url),
        ),
        projection,
    )


@router.put(
    "/Users/{user_id}",
    response_model=ScimUserResource,
    response_class=SCIMJSONResponse,
    responses=SCIM_USER_RESPONSES,
    status_code=status.HTTP_200_OK,
    summary="Replace a SCIM user",
    description=(
        "Performs SCIM full-replacement semantics for mutable User "
        "attributes. The SCIM `id` and AccessIQ record identity are preserved."
    ),
    openapi_extra={"requestBody": SCIM_USER_REQUEST_BODY},
)
def replace_user(
    user_id: str,
    request: Request,
    payload: Any = Body(default=None, media_type=SCIM_MEDIA_TYPE),
    current_user: User = Depends(require_scim_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    result = replace_scim_user(
        db=db,
        actor=current_user,
        user_id=user_id,
        payload=payload,
        base_url=str(request.base_url),
    )

    return result.resource


@router.patch(
    "/Users/{user_id}",
    response_model=ScimUserResource,
    response_class=SCIMJSONResponse,
    responses=SCIM_USER_RESPONSES,
    status_code=status.HTTP_200_OK,
    summary="Patch a SCIM user",
    description=(
        "Applies SCIM PATCH operations to User attributes. Supports `add`, "
        "`replace`, and `remove` for `displayName`, `active`, and `userName` "
        "where compatible with AccessIQ's required user fields."
    ),
    openapi_extra={"requestBody": SCIM_PATCH_REQUEST_BODY},
)
def patch_user(
    user_id: str,
    request: Request,
    payload: Any = Body(default=None, media_type=SCIM_MEDIA_TYPE),
    current_user: User = Depends(require_scim_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    result = patch_scim_user(
        db=db,
        actor=current_user,
        user_id=user_id,
        payload=payload,
        base_url=str(request.base_url),
    )

    return result.resource


@router.get(
    "/Schemas",
    response_model=ScimListResponse,
    response_class=SCIMJSONResponse,
    responses=SCIM_ERROR_RESPONSES,
    status_code=status.HTTP_200_OK,
    summary="List SCIM schemas",
    description=(
        "Returns metadata for the core User schema, core Group schema, and "
        "Enterprise User extension. User and group provisioning arrive in "
        "future milestones."
    ),
)
def list_schemas() -> ScimListResponse:
    schemas = build_schemas()
    resources = [schema.model_dump(exclude_none=True) for schema in schemas]
    return ScimListResponse(
        totalResults=len(resources),
        itemsPerPage=len(resources),
        Resources=resources,
    )
