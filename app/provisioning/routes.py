from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ProvisioningHistory, User
from ..rbac import require_roles
from ..schemas import ProvisioningHistoryResponse, ProvisioningJobResponse
from ..services.provisioning_job_service import (
    ProvisioningHistoryFilters,
    ProvisioningJobFilters,
    ProvisioningJobNotFoundError,
    ProvisioningJobService,
    UnsupportedProvisioningSortFieldError,
    UnsupportedProvisioningSortOrderError,
    history_details_to_dict,
)

router = APIRouter(prefix="/provisioning", tags=["Provisioning"])


@router.get(
    "/jobs",
    response_model=list[ProvisioningJobResponse],
    summary="List provisioning jobs",
    description=(
        "Lists persisted connector provisioning jobs. Supports pagination, "
        "filtering by connector, operation, status, correlation ID, target "
        "type, and target ID, plus sorting by common job fields."
    ),
)
def list_provisioning_jobs(
    connector: str | None = None,
    operation: str | None = None,
    job_status: str | None = Query(default=None, alias="status"),
    correlation_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    start_index: int = Query(default=1, ge=1),
    count: int = Query(default=100, ge=1, le=500),
    sort_by: str | None = Query(default="created_at"),
    sort_order: str = Query(default="descending"),
    current_user: User = Depends(
        require_roles("security_admin", "iam_admin", "auditor")
    ),
    db: Session = Depends(get_db),
) -> list[ProvisioningJobResponse]:
    del current_user
    service = ProvisioningJobService(db)
    try:
        return service.list_jobs(
            filters=ProvisioningJobFilters(
                connector=connector,
                operation=operation,
                status=job_status,
                correlation_id=correlation_id,
                target_type=target_type,
                target_id=target_id,
            ),
            offset=start_index - 1,
            limit=count,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except (
        UnsupportedProvisioningSortFieldError,
        UnsupportedProvisioningSortOrderError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/jobs/{job_id}",
    response_model=ProvisioningJobResponse,
    summary="Get provisioning job",
    description="Returns one provisioning job by ID.",
)
def get_provisioning_job(
    job_id: int,
    current_user: User = Depends(
        require_roles("security_admin", "iam_admin", "auditor")
    ),
    db: Session = Depends(get_db),
) -> ProvisioningJobResponse:
    del current_user
    service = ProvisioningJobService(db)
    try:
        return service.lookup_job(job_id)
    except ProvisioningJobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provisioning job not found",
        ) from exc


@router.get(
    "/history",
    response_model=list[ProvisioningHistoryResponse],
    summary="List provisioning history",
    description=(
        "Lists immutable provisioning history entries. Supports pagination, "
        "filtering by job, connector, operation, event type, status, and "
        "correlation ID, plus sorting by common history fields."
    ),
)
def list_provisioning_history(
    job_id: int | None = None,
    connector: str | None = None,
    operation: str | None = None,
    event_type: str | None = None,
    history_status: str | None = Query(default=None, alias="status"),
    correlation_id: str | None = None,
    start_index: int = Query(default=1, ge=1),
    count: int = Query(default=100, ge=1, le=500),
    sort_by: str | None = Query(default="created_at"),
    sort_order: str = Query(default="descending"),
    current_user: User = Depends(
        require_roles("security_admin", "iam_admin", "auditor")
    ),
    db: Session = Depends(get_db),
) -> list[ProvisioningHistoryResponse]:
    del current_user
    service = ProvisioningJobService(db)
    try:
        history = service.list_history(
            filters=ProvisioningHistoryFilters(
                job_id=job_id,
                connector=connector,
                operation=operation,
                event_type=event_type,
                status=history_status,
                correlation_id=correlation_id,
            ),
            offset=start_index - 1,
            limit=count,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except (
        UnsupportedProvisioningSortFieldError,
        UnsupportedProvisioningSortOrderError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return [_history_to_response(entry) for entry in history]


def _history_to_response(
    history: ProvisioningHistory,
) -> ProvisioningHistoryResponse:
    return ProvisioningHistoryResponse(
        id=history.id,
        job_id=history.job_id,
        correlation_id=history.correlation_id,
        connector=history.connector,
        operation=history.operation,
        event_type=history.event_type,
        status=history.status,
        message=history.message,
        attempt=history.attempt,
        retryable=history.retryable,
        duration_ms=history.duration_ms,
        details=history_details_to_dict(history),
        created_at=history.created_at,
    )
