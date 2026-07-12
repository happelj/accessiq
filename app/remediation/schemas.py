from datetime import datetime

from pydantic import BaseModel, Field

from .enums import RemediationStatus, RemediationType


class RemediationJobResponse(BaseModel):
    id: int
    campaign_id: int
    review_item_id: int
    provisioning_job_id: int | None
    correlation_id: str
    remediation_type: RemediationType
    status: RemediationStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    last_error: str | None
    initiated_by: int


class CampaignRemediationResponse(BaseModel):
    campaign_id: int = Field(description="Certification campaign remediated.")
    created_jobs: int = Field(description="Number of remediation jobs created.")
    executed_jobs: int = Field(description="Number of remediation jobs executed.")
    skipped_decisions: int = Field(
        description="Number of non-remediable decisions skipped."
    )
    jobs: list[RemediationJobResponse]
