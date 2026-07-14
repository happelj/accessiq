from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..dependencies import get_campaign_service, get_review_service
from ..models import User
from ..rbac import require_roles
from .enums import CampaignStatus, CertificationDecisionValue, ReviewItemStatus
from .models import CertificationCampaign, CertificationReviewItem
from .schemas import (
    CampaignCreateRequest,
    CampaignResponse,
    CampaignSummaryResponse,
    DecisionRequest,
    ReviewItemResponse,
)
from .services import (
    CampaignFilters,
    CampaignNotFoundError,
    CampaignService,
    DuplicateCampaignNameError,
    GovernanceServiceError,
    IncompleteCampaignError,
    InvalidCampaignTransitionError,
    MissingReviewerError,
    ReviewItemFilters,
    ReviewItemNotFoundError,
    ReviewService,
    UnsupportedGovernanceSortFieldError,
    UnsupportedGovernanceSortOrderError,
    campaign_completion_percentage,
)

router = APIRouter(prefix="/access-reviews", tags=["Access Reviews"])

READ_ROLES = ("security_admin", "iam_admin", "auditor")
WRITE_ROLES = ("security_admin", "iam_admin")


@router.post(
    "/campaigns",
    response_model=CampaignResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a certification campaign",
    description=(
        "Creates a draft access certification campaign. Review items are "
        "generated from current access assignments when the campaign starts."
    ),
)
def create_campaign(
    payload: CampaignCreateRequest = Body(
        ...,
        openapi_examples={
            "quarterly": {
                "summary": "Quarterly privileged access review",
                "value": {
                    "name": "Q3 Privileged Access Review",
                    "description": (
                        "Quarterly review of active application entitlements."
                    ),
                    "reviewer_id": 1,
                },
            }
        },
    ),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignResponse:
    db = service.db
    try:
        campaign = service.create_campaign(
            name=payload.name,
            description=payload.description,
            reviewer_id=payload.reviewer_id,
            actor=current_user,
        )
        _commit(db)
    except GovernanceServiceError as exc:
        db.rollback()
        _raise_governance_http_error(exc)
    except SQLAlchemyError as exc:
        db.rollback()
        raise _database_error() from exc

    service.publish_pending_events()

    return _campaign_to_response(campaign)


@router.get(
    "/campaigns",
    response_model=list[CampaignResponse],
    summary="List certification campaigns",
    description=(
        "Lists certification campaigns with pagination, filtering by status, "
        "creator, and default reviewer, and sorting by common campaign fields."
    ),
)
def list_campaigns(
    campaign_status: CampaignStatus | None = Query(default=None, alias="status"),
    created_by: int | None = None,
    reviewer_id: int | None = None,
    start_index: int = Query(default=1, ge=1),
    count: int = Query(default=100, ge=1, le=500),
    sort_by: str | None = Query(default="created_at"),
    sort_order: str = Query(default="descending"),
    current_user: User = Depends(require_roles(*READ_ROLES)),
    service: CampaignService = Depends(get_campaign_service),
) -> list[CampaignResponse]:
    del current_user
    try:
        campaigns = service.list_campaigns(
            filters=CampaignFilters(
                status=campaign_status.value if campaign_status is not None else None,
                created_by=created_by,
                reviewer_id=reviewer_id,
            ),
            offset=start_index - 1,
            limit=count,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except GovernanceServiceError as exc:
        _raise_governance_http_error(exc)

    return [_campaign_to_response(campaign) for campaign in campaigns]


@router.get(
    "/campaigns/{campaign_id}",
    response_model=CampaignResponse,
    summary="Get a certification campaign",
    description="Returns one certification campaign by ID.",
)
def get_campaign(
    campaign_id: int,
    current_user: User = Depends(require_roles(*READ_ROLES)),
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignResponse:
    del current_user
    try:
        campaign = service.lookup_campaign(campaign_id)
    except GovernanceServiceError as exc:
        _raise_governance_http_error(exc)

    return _campaign_to_response(campaign)


@router.get(
    "/campaigns/{campaign_id}/summary",
    response_model=CampaignSummaryResponse,
    summary="Summarize a certification campaign",
    description=(
        "Returns pending and completed item counts, decision counts, and "
        "completion percentage for one campaign."
    ),
)
def get_campaign_summary(
    campaign_id: int,
    current_user: User = Depends(require_roles(*READ_ROLES)),
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignSummaryResponse:
    del current_user
    try:
        campaign = service.summarize_campaign(campaign_id)
    except GovernanceServiceError as exc:
        _raise_governance_http_error(exc)

    return _campaign_to_summary_response(campaign)


@router.post(
    "/campaigns/{campaign_id}/start",
    response_model=CampaignResponse,
    summary="Start a certification campaign",
    description=(
        "Transitions a draft campaign to active and generates one review item "
        "for each current access assignment. No provisioning action is taken."
    ),
)
def start_campaign(
    campaign_id: int,
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignResponse:
    db = service.db
    try:
        campaign = service.start_campaign(campaign_id, actor=current_user)
        _commit(db)
    except GovernanceServiceError as exc:
        db.rollback()
        _raise_governance_http_error(exc)
    except SQLAlchemyError as exc:
        db.rollback()
        raise _database_error() from exc

    service.publish_pending_events()

    return _campaign_to_response(campaign)


@router.post(
    "/campaigns/{campaign_id}/cancel",
    response_model=CampaignResponse,
    summary="Cancel a certification campaign",
    description="Cancels a draft or active campaign without remediating access.",
)
def cancel_campaign(
    campaign_id: int,
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignResponse:
    db = service.db
    try:
        campaign = service.cancel_campaign(campaign_id, actor=current_user)
        _commit(db)
    except GovernanceServiceError as exc:
        db.rollback()
        _raise_governance_http_error(exc)
    except SQLAlchemyError as exc:
        db.rollback()
        raise _database_error() from exc

    service.publish_pending_events()

    return _campaign_to_response(campaign)


@router.post(
    "/campaigns/{campaign_id}/complete",
    response_model=CampaignResponse,
    summary="Complete a certification campaign",
    description=(
        "Completes an active campaign after all review items have decisions. "
        "Recorded revoke decisions are retained for future remediation."
    ),
)
def complete_campaign(
    campaign_id: int,
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignResponse:
    db = service.db
    try:
        campaign = service.complete_campaign(campaign_id, actor=current_user)
        _commit(db)
    except GovernanceServiceError as exc:
        db.rollback()
        _raise_governance_http_error(exc)
    except SQLAlchemyError as exc:
        db.rollback()
        raise _database_error() from exc

    service.publish_pending_events()

    return _campaign_to_response(campaign)


@router.get(
    "/campaigns/{campaign_id}/items",
    response_model=list[ReviewItemResponse],
    summary="List review items for a campaign",
    description=(
        "Lists generated review items with pagination and optional filters by "
        "status, reviewer, and decision."
    ),
)
def list_review_items(
    campaign_id: int,
    item_status: ReviewItemStatus | None = Query(default=None, alias="status"),
    reviewer_id: int | None = None,
    decision: CertificationDecisionValue | None = None,
    start_index: int = Query(default=1, ge=1),
    count: int = Query(default=100, ge=1, le=500),
    sort_by: str | None = Query(default="id"),
    sort_order: str = Query(default="ascending"),
    current_user: User = Depends(require_roles(*READ_ROLES)),
    service: ReviewService = Depends(get_review_service),
) -> list[ReviewItemResponse]:
    del current_user
    try:
        items = service.list_review_items(
            campaign_id,
            filters=ReviewItemFilters(
                status=item_status.value if item_status is not None else None,
                reviewer_id=reviewer_id,
                decision=decision.value if decision is not None else None,
            ),
            offset=start_index - 1,
            limit=count,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except GovernanceServiceError as exc:
        _raise_governance_http_error(exc)

    return [_review_item_to_response(item) for item in items]


@router.get(
    "/items/{item_id}",
    response_model=ReviewItemResponse,
    summary="Get a review item",
    description="Returns one generated access review item by ID.",
)
def get_review_item(
    item_id: int,
    current_user: User = Depends(require_roles(*READ_ROLES)),
    service: ReviewService = Depends(get_review_service),
) -> ReviewItemResponse:
    del current_user
    try:
        item = service.lookup_review_item(item_id)
    except GovernanceServiceError as exc:
        _raise_governance_http_error(exc)

    return _review_item_to_response(item)


@router.post(
    "/items/{item_id}/decision",
    response_model=ReviewItemResponse,
    summary="Record a certification decision",
    description=(
        "Records or updates a governance decision for one review item. "
        "APPROVE, REVOKE, and ABSTAIN decisions are stored for governance and "
        "future remediation only; this endpoint does not remove access."
    ),
)
def record_decision(
    item_id: int,
    payload: DecisionRequest = Body(
        ...,
        openapi_examples={
            "revoke": {
                "summary": "Mark access for future remediation",
                "value": {
                    "decision": "REVOKE",
                    "comments": "Access is no longer required for this role.",
                },
            },
            "approve": {
                "summary": "Certify access",
                "value": {
                    "decision": "APPROVE",
                    "comments": "Access is still required.",
                },
            },
        },
    ),
    current_user: User = Depends(require_roles(*READ_ROLES)),
    service: ReviewService = Depends(get_review_service),
) -> ReviewItemResponse:
    db = service.db
    try:
        item = service.record_decision(
            item_id,
            decision=payload.decision,
            comments=payload.comments,
            actor=current_user,
        )
        _commit(db)
    except GovernanceServiceError as exc:
        db.rollback()
        _raise_governance_http_error(exc)
    except SQLAlchemyError as exc:
        db.rollback()
        raise _database_error() from exc

    service.publish_pending_events()

    return _review_item_to_response(item)


def _campaign_to_response(campaign: CertificationCampaign) -> CampaignResponse:
    return CampaignResponse(
        id=campaign.id,
        name=campaign.name,
        description=campaign.description,
        status=CampaignStatus(campaign.status),
        created_by=campaign.created_by,
        default_reviewer_id=campaign.default_reviewer_id,
        created_at=campaign.created_at,
        started_at=campaign.started_at,
        completed_at=campaign.completed_at,
        cancelled_at=campaign.cancelled_at,
        total_items=campaign.total_items,
        completed_items=campaign.completed_items,
        approval_count=campaign.approval_count,
        revocation_count=campaign.revocation_count,
        abstain_count=campaign.abstain_count,
        completion_percentage=campaign_completion_percentage(campaign),
    )


def _campaign_to_summary_response(
    campaign: CertificationCampaign,
) -> CampaignSummaryResponse:
    return CampaignSummaryResponse(
        campaign_id=campaign.id,
        status=CampaignStatus(campaign.status),
        total_items=campaign.total_items,
        pending_items=campaign.total_items - campaign.completed_items,
        completed_items=campaign.completed_items,
        approval_count=campaign.approval_count,
        revocation_count=campaign.revocation_count,
        abstain_count=campaign.abstain_count,
        completion_percentage=campaign_completion_percentage(campaign),
    )


def _review_item_to_response(
    item: CertificationReviewItem,
) -> ReviewItemResponse:
    decision_record = item.decision_record
    return ReviewItemResponse(
        id=item.id,
        campaign_id=item.campaign_id,
        access_assignment_id=item.access_assignment_id,
        user_id=item.user_id,
        user_name=item.user.name,
        user_email=item.user.email,
        application_id=item.application_id,
        application=item.application.name,
        entitlement_id=item.entitlement_id,
        entitlement=item.entitlement.name,
        group_id=item.group_id,
        reviewer_id=item.reviewer_id,
        reviewer_email=item.reviewer.email,
        status=ReviewItemStatus(item.status),
        decision=(
            CertificationDecisionValue(decision_record.decision)
            if decision_record is not None
            else None
        ),
        comments=decision_record.comments if decision_record is not None else None,
        reviewed_at=item.reviewed_at,
        created_at=item.created_at,
    )


def _commit(db: Session) -> None:
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def _database_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database operation failed",
    )


def _raise_governance_http_error(error: GovernanceServiceError) -> None:
    if isinstance(error, DuplicateCampaignNameError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Certification campaign already exists",
        ) from error

    if isinstance(error, (CampaignNotFoundError, ReviewItemNotFoundError)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    if isinstance(error, MissingReviewerError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reviewer not found",
        ) from error

    if isinstance(
        error,
        (
            InvalidCampaignTransitionError,
            IncompleteCampaignError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    if isinstance(
        error,
        (
            UnsupportedGovernanceSortFieldError,
            UnsupportedGovernanceSortOrderError,
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
