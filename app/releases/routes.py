from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_release_service
from ..models import User
from ..rbac import require_roles
from .schemas import (
    CurrentReleaseResponse,
    DeploymentHistoryResponse,
    ReleaseMetadataResponse,
)
from .services import (
    DeploymentHistoryFilters,
    ReleaseService,
    deployment_to_response,
)

router = APIRouter(tags=["Releases"])

READ_ROLES = ("security_admin", "iam_admin", "auditor")


@router.get(
    "/version",
    response_model=ReleaseMetadataResponse,
    summary="Read release metadata",
    description=(
        "Returns the current AccessIQ release metadata captured from runtime "
        "configuration, including Git, image, Helm, Terraform, and environment data."
    ),
)
def get_version(
    service: ReleaseService = Depends(get_release_service),
) -> ReleaseMetadataResponse:
    return service.current_metadata()


@router.get(
    "/releases",
    response_model=list[DeploymentHistoryResponse],
    summary="List deployment history",
    description=(
        "Requires a security_admin, iam_admin, or auditor bearer token. Returns "
        "application-level deployment records newest first."
    ),
)
def list_releases(
    environment: str | None = None,
    release_status: str | None = Query(default=None, alias="status"),
    start_index: int = Query(default=1, ge=1),
    count: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(require_roles(*READ_ROLES)),
    service: ReleaseService = Depends(get_release_service),
) -> list[DeploymentHistoryResponse]:
    del current_user
    deployments = service.list_deployments(
        filters=DeploymentHistoryFilters(
            environment=environment,
            status=release_status,
        ),
        offset=start_index - 1,
        limit=count,
    )
    return [deployment_to_response(deployment) for deployment in deployments]


@router.get(
    "/releases/current",
    response_model=CurrentReleaseResponse,
    summary="Read current release",
    description=(
        "Requires a security_admin, iam_admin, or auditor bearer token. Returns "
        "current release metadata and the latest deployment record for this environment."
    ),
)
def get_current_release(
    current_user: User = Depends(require_roles(*READ_ROLES)),
    service: ReleaseService = Depends(get_release_service),
) -> CurrentReleaseResponse:
    del current_user
    deployment = service.current_deployment()
    return CurrentReleaseResponse(
        metadata=service.current_metadata(),
        deployment=(
            deployment_to_response(deployment) if deployment is not None else None
        ),
    )
