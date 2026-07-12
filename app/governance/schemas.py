from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import CampaignStatus, CertificationDecisionValue, ReviewItemStatus


class CampaignCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=150,
        description="Unique certification campaign name.",
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional campaign description and scope notes.",
    )
    reviewer_id: int = Field(
        ge=1,
        description="Default reviewer assigned to generated review items.",
    )


class CampaignResponse(BaseModel):
    id: int
    name: str
    description: str | None
    status: CampaignStatus
    created_by: int
    default_reviewer_id: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    total_items: int
    completed_items: int
    approval_count: int
    revocation_count: int
    abstain_count: int
    completion_percentage: float


class CampaignSummaryResponse(BaseModel):
    campaign_id: int
    status: CampaignStatus
    total_items: int
    pending_items: int
    completed_items: int
    approval_count: int
    revocation_count: int
    abstain_count: int
    completion_percentage: float


class ReviewItemResponse(BaseModel):
    id: int
    campaign_id: int
    access_assignment_id: int
    user_id: int
    user_name: str
    user_email: str
    application_id: int
    application: str
    entitlement_id: int
    entitlement: str
    group_id: int | None
    reviewer_id: int
    reviewer_email: str
    status: ReviewItemStatus
    decision: CertificationDecisionValue | None
    comments: str | None
    reviewed_at: datetime | None
    created_at: datetime


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: CertificationDecisionValue = Field(
        description="Governance decision to approve, revoke, or abstain.",
    )
    comments: str | None = Field(
        default=None,
        max_length=2000,
        description="Reviewer comments explaining the decision.",
    )
