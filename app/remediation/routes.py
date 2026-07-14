from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError

from ..dependencies import get_remediation_service
from ..models import User
from ..rbac import require_roles
from .enums import RemediationStatus, RemediationType
from .models import RemediationJob
from .schemas import CampaignRemediationResponse, RemediationJobResponse
from .services import (
    CampaignRemediationResult,
    DuplicateRemediationJobError,
    InvalidRemediationCampaignStateError,
    RemediationCampaignNotFoundError,
    RemediationJobFilters,
    RemediationJobNotFoundError,
    RemediationReviewItemNotFoundError,
    RemediationService,
    RemediationServiceError,
    UnsupportedRemediationConnectorError,
    UnsupportedRemediationDecisionError,
    UnsupportedRemediationSortFieldError,
    UnsupportedRemediationSortOrderError,
)

router = APIRouter(tags=["Remediation"])

REMEDIATION_ROLES = ("security_admin", "iam_admin")


@router.post(
    "/access-reviews/campaigns/{campaign_id}/remediate",
    response_model=CampaignRemediationResponse,
    summary="Execute campaign remediation",
    description=(
        "Creates and executes remediation jobs for REVOKE decisions in a "
        "completed certification campaign. Execution reuses the provisioning "
        "orchestrator, connector registry, provisioning jobs, provisioning "
        "history, audit events, and domain events."
    ),
)
def remediate_campaign(
    campaign_id: int,
    current_user: User = Depends(require_roles(*REMEDIATION_ROLES)),
    service: RemediationService = Depends(get_remediation_service),
) -> CampaignRemediationResponse:
    db = service.db
    try:
        result = service.execute_campaign(campaign_id, actor=current_user)
        db.commit()
    except RemediationServiceError as exc:
        db.rollback()
        _raise_remediation_http_error(exc)
    except SQLAlchemyError as exc:
        db.rollback()
        raise _database_error() from exc

    service.publish_pending_events()

    return _campaign_result_to_response(result)


@router.get(
    "/remediation/jobs",
    response_model=list[RemediationJobResponse],
    summary="List remediation jobs",
    description=(
        "Lists governance remediation jobs with pagination and filters by "
        "campaign, review item, status, type, and correlation ID."
    ),
)
def list_remediation_jobs(
    campaign_id: int | None = None,
    review_item_id: int | None = None,
    job_status: RemediationStatus | None = Query(default=None, alias="status"),
    remediation_type: RemediationType | None = None,
    correlation_id: str | None = None,
    start_index: int = Query(default=1, ge=1),
    count: int = Query(default=100, ge=1, le=500),
    sort_by: str | None = Query(default="created_at"),
    sort_order: str = Query(default="descending"),
    current_user: User = Depends(require_roles(*REMEDIATION_ROLES)),
    service: RemediationService = Depends(get_remediation_service),
) -> list[RemediationJobResponse]:
    del current_user
    try:
        jobs = service.list_jobs(
            filters=RemediationJobFilters(
                campaign_id=campaign_id,
                review_item_id=review_item_id,
                status=job_status.value if job_status is not None else None,
                remediation_type=(
                    remediation_type.value if remediation_type is not None else None
                ),
                correlation_id=correlation_id,
            ),
            offset=start_index - 1,
            limit=count,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except RemediationServiceError as exc:
        _raise_remediation_http_error(exc)

    return [_job_to_response(job) for job in jobs]


@router.get(
    "/remediation/jobs/{job_id}",
    response_model=RemediationJobResponse,
    summary="Get remediation job",
    description="Returns one governance remediation job by ID.",
)
def get_remediation_job(
    job_id: int,
    current_user: User = Depends(require_roles(*REMEDIATION_ROLES)),
    service: RemediationService = Depends(get_remediation_service),
) -> RemediationJobResponse:
    del current_user
    try:
        job = service.lookup_job(job_id)
    except RemediationServiceError as exc:
        _raise_remediation_http_error(exc)

    return _job_to_response(job)


def _campaign_result_to_response(
    result: CampaignRemediationResult,
) -> CampaignRemediationResponse:
    return CampaignRemediationResponse(
        campaign_id=result.campaign_id,
        created_jobs=result.created_jobs,
        executed_jobs=result.executed_jobs,
        skipped_decisions=result.skipped_decisions,
        jobs=[_job_to_response(job) for job in result.jobs],
    )


def _job_to_response(job: RemediationJob) -> RemediationJobResponse:
    return RemediationJobResponse(
        id=job.id,
        campaign_id=job.campaign_id,
        review_item_id=job.review_item_id,
        provisioning_job_id=job.provisioning_job_id,
        correlation_id=job.correlation_id,
        remediation_type=RemediationType(job.remediation_type),
        status=RemediationStatus(job.status),
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        last_error=job.last_error,
        initiated_by=job.initiated_by,
    )


def _database_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database operation failed",
    )


def _raise_remediation_http_error(error: RemediationServiceError) -> None:
    if isinstance(
        error,
        (
            RemediationCampaignNotFoundError,
            RemediationReviewItemNotFoundError,
            RemediationJobNotFoundError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    if isinstance(
        error,
        (
            DuplicateRemediationJobError,
            InvalidRemediationCampaignStateError,
            UnsupportedRemediationDecisionError,
            UnsupportedRemediationConnectorError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    if isinstance(
        error,
        (
            UnsupportedRemediationSortFieldError,
            UnsupportedRemediationSortOrderError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=str(error),
    ) from error
