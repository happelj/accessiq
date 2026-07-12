from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..models import User


class DelegationAssignment(Base):
    __tablename__ = "delegation_assignments"
    __table_args__ = (
        UniqueConstraint(
            "delegate_user_id",
            "scope_type",
            "scope_id",
            "delegation_role",
            "active",
            name="uq_delegation_assignments_active_scope_role",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    delegate_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    scope_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    scope_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    delegation_role: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )
    created_by: Mapped[int] = mapped_column(
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
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=True,
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        index=True,
        nullable=False,
    )

    delegate: Mapped[User] = relationship(foreign_keys=[delegate_user_id])
    creator: Mapped[User] = relationship(foreign_keys=[created_by])
