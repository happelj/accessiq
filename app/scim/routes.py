from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from ..rbac import require_roles
from .constants import SCIM_BASE_PATH, SCIM_MEDIA_TYPE
from .errors import SCIM_ERROR_RESPONSES
from .models import (
    build_resource_types,
    build_schemas,
    build_service_provider_config,
)
from .pagination import ScimListResponse
from .schemas import ServiceProviderConfig


class SCIMJSONResponse(JSONResponse):
    media_type = SCIM_MEDIA_TYPE


require_scim_admin = require_roles("security_admin", "iam_admin")

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
        "Provisioning endpoints are planned for Milestone 6B."
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
