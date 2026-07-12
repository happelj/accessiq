from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..governance.models import CertificationCampaign, CertificationReviewItem
from ..models import ProvisioningJob, User


class RemediationJob(Base):
    __tablename__ = "remediation_jobs"
    __table_args__ = (
        UniqueConstraint(
            "review_item_id",
            name="uq_remediation_jobs_review_item_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("certification_campaigns.id"),
        index=True,
        nullable=False,
    )
    review_item_id: Mapped[int] = mapped_column(
        ForeignKey("certification_review_items.id"),
        index=True,
        nullable=False,
    )
    provisioning_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("provisioning_jobs.id"),
        index=True,
        nullable=True,
    )
    correlation_id: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )
    remediation_type: Mapped[str] = mapped_column(
        String(50),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    initiated_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )

    campaign: Mapped[CertificationCampaign] = relationship()
    review_item: Mapped[CertificationReviewItem] = relationship()
    provisioning_job: Mapped[ProvisioningJob | None] = relationship()
    initiator: Mapped[User] = relationship()
