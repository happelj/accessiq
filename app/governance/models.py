from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..models import AccessAssignment, Application, Entitlement, Group, User


class CertificationCampaign(Base):
    __tablename__ = "certification_campaigns"
    __table_args__ = (UniqueConstraint("name", name="uq_certification_campaigns_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    default_reviewer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
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
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    total_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    approval_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revocation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    abstain_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    creator: Mapped[User] = relationship(foreign_keys=[created_by])
    default_reviewer: Mapped[User] = relationship(foreign_keys=[default_reviewer_id])
    review_items: Mapped[list[CertificationReviewItem]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
    )
    decisions: Mapped[list[CertificationDecision]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
    )


class CertificationReviewItem(Base):
    __tablename__ = "certification_review_items"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "access_assignment_id",
            name="uq_certification_review_items_campaign_assignment",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("certification_campaigns.id"),
        index=True,
        nullable=False,
    )
    access_assignment_id: Mapped[int] = mapped_column(
        ForeignKey("access_assignments.id"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id"),
        index=True,
        nullable=False,
    )
    entitlement_id: Mapped[int] = mapped_column(
        ForeignKey("entitlements.id"),
        index=True,
        nullable=False,
    )
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("groups.id"),
        index=True,
        nullable=True,
    )
    reviewer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
        nullable=False,
    )

    campaign: Mapped[CertificationCampaign] = relationship(
        back_populates="review_items",
    )
    access_assignment: Mapped[AccessAssignment] = relationship()
    user: Mapped[User] = relationship(foreign_keys=[user_id])
    application: Mapped[Application] = relationship()
    entitlement: Mapped[Entitlement] = relationship()
    group: Mapped[Group | None] = relationship()
    reviewer: Mapped[User] = relationship(foreign_keys=[reviewer_id])
    decision_record: Mapped[CertificationDecision | None] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        uselist=False,
    )


class CertificationDecision(Base):
    __tablename__ = "certification_decisions"
    __table_args__ = (
        UniqueConstraint("review_item_id", name="uq_certification_decisions_item"),
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
    reviewer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    campaign: Mapped[CertificationCampaign] = relationship(
        back_populates="decisions",
    )
    item: Mapped[CertificationReviewItem] = relationship(
        back_populates="decision_record",
    )
    reviewer: Mapped[User] = relationship()
