from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
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
    group_memberships: Mapped[list[GroupMember]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    enterprise_profile: Mapped[EnterpriseUserProfile | None] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="EnterpriseUserProfile.user_id",
        uselist=False,
    )
    managed_enterprise_profiles: Mapped[list[EnterpriseUserProfile]] = relationship(
        back_populates="manager",
        foreign_keys="EnterpriseUserProfile.manager_id",
    )


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    memberships: Mapped[list[GroupMember]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint(
            "group_id",
            "user_id",
            name="uq_group_members_group_user",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    group: Mapped[Group] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="group_memberships")


class EnterpriseUserProfile(Base):
    __tablename__ = "enterprise_user_profiles"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            name="uq_enterprise_user_profiles_user_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    employee_number: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=True,
    )
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    division: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cost_center: Mapped[str | None] = mapped_column(String(100), nullable=True)
    organization: Mapped[str | None] = mapped_column(String(100), nullable=True)
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    user: Mapped[User] = relationship(
        back_populates="enterprise_profile",
        foreign_keys=[user_id],
    )
    manager: Mapped[User | None] = relationship(
        back_populates="managed_enterprise_profiles",
        foreign_keys=[manager_id],
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
    correlation_id: Mapped[str | None] = mapped_column(
        String(100),
        index=True,
        nullable=True,
    )
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


class ProvisioningJob(Base):
    __tablename__ = "provisioning_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    correlation_id: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )
    connector: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    operation: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    target_id: Mapped[str | None] = mapped_column(
        String(100),
        index=True,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    history_entries: Mapped[list[ProvisioningHistory]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )


class ProvisioningHistory(Base):
    __tablename__ = "provisioning_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("provisioning_jobs.id"),
        index=True,
        nullable=False,
    )
    correlation_id: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )
    connector: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    operation: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
        nullable=False,
    )
    job: Mapped[ProvisioningJob] = relationship(back_populates="history_entries")


class ReleaseDeployment(Base):
    __tablename__ = "release_deployments"

    id: Mapped[int] = mapped_column(primary_key=True)
    environment: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    deployed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
        nullable=False,
    )
    version: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    git_sha: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    git_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    build_timestamp: Mapped[str | None] = mapped_column(String(100), nullable=True)
    docker_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_digest: Mapped[str | None] = mapped_column(String(500), nullable=True)
    helm_chart_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    helm_revision: Mapped[str | None] = mapped_column(String(50), nullable=True)
    terraform_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    operator: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
