from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    operator_role: Mapped[str] = mapped_column(
        String(50),
        default="employee",
        nullable=False,
    )
    access_assignments: Mapped[list[AccessAssignment]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    requested_audit_events: Mapped[list[AuditEvent]] = relationship(
        back_populates="requester",
        foreign_keys="AuditEvent.requester_id",
    )
    targeted_audit_events: Mapped[list[AuditEvent]] = relationship(
        back_populates="target_user",
        foreign_keys="AuditEvent.target_user_id",
    )


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    entitlements: Mapped[list[Entitlement]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
    )


class Entitlement(Base):
    __tablename__ = "entitlements"
    __table_args__ = (
        UniqueConstraint(
            "application_id",
            "slug",
            name="uq_entitlements_application_slug",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id"),
        nullable=False,
    )
    application: Mapped[Application] = relationship(back_populates="entitlements")
    access_assignments: Mapped[list[AccessAssignment]] = relationship(
        back_populates="entitlement",
        cascade="all, delete-orphan",
    )


class AccessAssignment(Base):
    __tablename__ = "access_assignments"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "entitlement_id",
            name="uq_access_assignments_user_entitlement",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    entitlement_id: Mapped[int] = mapped_column(
        ForeignKey("entitlements.id"),
        nullable=False,
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    user: Mapped[User] = relationship(back_populates="access_assignments")
    entitlement: Mapped[Entitlement] = relationship(
        back_populates="access_assignments",
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    target_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id"),
        nullable=False,
    )
    entitlement_id: Mapped[int] = mapped_column(
        ForeignKey("entitlements.id"),
        nullable=False,
    )
    result: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
        nullable=False,
    )

    requester: Mapped[User] = relationship(
        back_populates="requested_audit_events",
        foreign_keys=[requester_id],
    )
    target_user: Mapped[User] = relationship(
        back_populates="targeted_audit_events",
        foreign_keys=[target_user_id],
    )
    application: Mapped[Application] = relationship()
    entitlement: Mapped[Entitlement] = relationship()
