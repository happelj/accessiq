from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql.elements import ColumnElement

from ..audit_service import create_audit_event
from ..connectors import ProvisioningOrchestrator, build_connector_registry
from ..connectors.results import ConnectorOperation, ConnectorStatus
from ..domain.events import (
    DomainEvent,
    RemediationCompleted,
    RemediationCreated,
    RemediationFailed,
    RemediationStarted,
    event_time,
)
from ..domain.publisher import publish_domain_events
from ..governance.enums import CampaignStatus, CertificationDecisionValue
from ..governance.models import (
    CertificationCampaign,
    CertificationDecision,
    CertificationReviewItem,
)
from ..models import Entitlement, ProvisioningJob, User
from .enums import RemediationStatus, RemediationType
from .models import RemediationJob
from .validation import connector_name_for_application

ACTION_REMEDIATION_CREATED = "remediation_created"
ACTION_REMEDIATION_STARTED = "remediation_started"
ACTION_REMEDIATION_COMPLETED = "remediation_completed"
ACTION_REMEDIATION_FAILED = "remediation_failed"

SUPPORTED_REMEDIATION_JOB_SORT_FIELDS: dict[str, ColumnElement[Any]] = {
    "id": RemediationJob.id,
    "created_at": RemediationJob.created_at,
    "started_at": RemediationJob.started_at,
    "completed_at": RemediationJob.completed_at,
    "status": RemediationJob.status,
    "remediation_type": RemediationJob.remediation_type,
}
SUPPORTED_SORT_ORDERS = {"ascending", "descending"}


@dataclass(frozen=True)
class RemediationJobFilters:
    campaign_id: int | None = None
    review_item_id: int | None = None
    status: str | None = None
    remediation_type: str | None = None
    correlation_id: str | None = None


@dataclass(frozen=True)
class CampaignRemediationResult:
    campaign_id: int
    created_jobs: int
    executed_jobs: int
    skipped_decisions: int
    jobs: list[RemediationJob]


class RemediationServiceError(Exception):
    """Base exception for remediation service failures."""


class RemediationCampaignNotFoundError(RemediationServiceError):
    def __init__(self, campaign_id: int) -> None:
        super().__init__(f"Certification campaign {campaign_id} was not found")
        self.campaign_id = campaign_id


class RemediationReviewItemNotFoundError(RemediationServiceError):
    def __init__(self, review_item_id: int) -> None:
        super().__init__(f"Certification review item {review_item_id} was not found")
        self.review_item_id = review_item_id


class RemediationJobNotFoundError(RemediationServiceError):
    def __init__(self, job_id: int) -> None:
        super().__init__(f"Remediation job {job_id} was not found")
        self.job_id = job_id


class DuplicateRemediationJobError(RemediationServiceError):
    def __init__(self, review_item_id: int) -> None:
        super().__init__(
            f"Remediation job already exists for review item {review_item_id}"
        )
        self.review_item_id = review_item_id


class InvalidRemediationCampaignStateError(RemediationServiceError):
    def __init__(self, campaign: CertificationCampaign) -> None:
        super().__init__(
            f"Campaign {campaign.id} must be COMPLETED before remediation"
        )
        self.campaign = campaign


class UnsupportedRemediationDecisionError(RemediationServiceError):
    def __init__(self, review_item_id: int) -> None:
        super().__init__(
            f"Review item {review_item_id} does not have a remediable decision"
        )
        self.review_item_id = review_item_id


class UnsupportedRemediationConnectorError(RemediationServiceError):
    def __init__(self, application_slug: str) -> None:
        super().__init__(
            f"No remediation connector is available for application "
            f"{application_slug!r}"
        )
        self.application_slug = application_slug


class UnsupportedRemediationSortFieldError(RemediationServiceError):
    def __init__(self, sort_by: str) -> None:
        super().__init__(f"Unsupported remediation sort field: {sort_by}")
        self.sort_by = sort_by


class UnsupportedRemediationSortOrderError(RemediationServiceError):
    def __init__(self, sort_order: str) -> None:
        super().__init__(f"Unsupported remediation sort order: {sort_order}")
        self.sort_order = sort_order


class RemediationService:
    def __init__(
        self,
        db: Session,
        *,
        orchestrator: ProvisioningOrchestrator | None = None,
    ) -> None:
        self.db = db
        self.orchestrator = orchestrator or ProvisioningOrchestrator(
            registry=build_connector_registry()
        )
        self.pending_events: list[DomainEvent] = []

    def create_job(
        self,
        review_item_id: int,
        *,
        remediation_type: RemediationType,
        actor: User,
        correlation_id: str | None = None,
    ) -> RemediationJob:
        item = self._lookup_review_item(review_item_id)
        if item.decision_record is None:
            raise UnsupportedRemediationDecisionError(item.id)
        if item.decision_record.decision != CertificationDecisionValue.REVOKE.value:
            raise UnsupportedRemediationDecisionError(item.id)

        self.prevent_duplicate_jobs(item.id)
        job = RemediationJob(
            campaign_id=item.campaign_id,
            review_item_id=item.id,
            correlation_id=correlation_id or str(uuid4()),
            remediation_type=remediation_type.value,
            status=RemediationStatus.PENDING.value,
            initiated_by=actor.id,
        )
        self.db.add(job)
        self.db.flush()
        self._record_job_audit(
            job,
            actor=actor,
            action=ACTION_REMEDIATION_CREATED,
            result="succeeded",
            reason=f"Remediation job {job.id} created",
        )
        self.pending_events.append(
            RemediationCreated(
                occurred_at=event_time(),
                remediation_job_id=job.id,
                campaign_id=job.campaign_id,
                review_item_id=job.review_item_id,
                remediation_type=job.remediation_type,
                correlation_id=job.correlation_id,
            )
        )

        return job

    def execute_job(
        self,
        job: RemediationJob,
        *,
        actor: User,
    ) -> RemediationJob:
        item = self._lookup_review_item(job.review_item_id)
        self.start_job(job, actor=actor)

        try:
            connector_name, operation, payload = self._operation_for_job(job, item)
            result = self.orchestrator.execute(
                connector_name=connector_name,
                operation=operation,
                payload=payload,
                correlation_id=job.correlation_id,
                db=self.db,
                requester_id=actor.id,
                target_user_id=item.user_id,
            )
            self._link_provisioning_job(job)

            if result.status == ConnectorStatus.SUCCESS:
                return self.complete_job(job, actor=actor)

            if result.status == ConnectorStatus.SKIPPED:
                return self.complete_job(
                    job,
                    actor=actor,
                    status=RemediationStatus.SKIPPED,
                    message=result.message,
                )

            return self.fail_job(job, actor=actor, message=result.message)
        except Exception as exc:
            return self.fail_job(job, actor=actor, message=str(exc))

    def start_job(self, job: RemediationJob, *, actor: User) -> RemediationJob:
        job.status = RemediationStatus.RUNNING.value
        job.started_at = _utc_now()
        job.last_error = None
        self.db.flush()
        self._record_job_audit(
            job,
            actor=actor,
            action=ACTION_REMEDIATION_STARTED,
            result="succeeded",
            reason=f"Remediation job {job.id} started",
        )
        self.pending_events.append(
            RemediationStarted(
                occurred_at=event_time(),
                remediation_job_id=job.id,
                campaign_id=job.campaign_id,
                review_item_id=job.review_item_id,
                remediation_type=job.remediation_type,
                correlation_id=job.correlation_id,
            )
        )

        return job

    def complete_job(
        self,
        job: RemediationJob,
        *,
        actor: User,
        status: RemediationStatus = RemediationStatus.COMPLETED,
        message: str | None = None,
    ) -> RemediationJob:
        job.status = status.value
        job.completed_at = _utc_now()
        job.last_error = None
        self.db.flush()
        self._record_job_audit(
            job,
            actor=actor,
            action=ACTION_REMEDIATION_COMPLETED,
            result="succeeded",
            reason=message or f"Remediation job {job.id} completed",
        )
        self.pending_events.append(
            RemediationCompleted(
                occurred_at=event_time(),
                remediation_job_id=job.id,
                campaign_id=job.campaign_id,
                review_item_id=job.review_item_id,
                remediation_type=job.remediation_type,
                status=job.status,
                provisioning_job_id=job.provisioning_job_id,
                correlation_id=job.correlation_id,
            )
        )

        return job

    def fail_job(
        self,
        job: RemediationJob,
        *,
        actor: User,
        message: str,
    ) -> RemediationJob:
        self._link_provisioning_job(job)
        job.status = RemediationStatus.FAILED.value
        job.completed_at = _utc_now()
        job.last_error = message
        self.db.flush()
        self._record_job_audit(
            job,
            actor=actor,
            action=ACTION_REMEDIATION_FAILED,
            result="denied",
            reason=f"Remediation job {job.id} failed: {message}",
        )
        self.pending_events.append(
            RemediationFailed(
                occurred_at=event_time(),
                remediation_job_id=job.id,
                campaign_id=job.campaign_id,
                review_item_id=job.review_item_id,
                remediation_type=job.remediation_type,
                message=message,
                correlation_id=job.correlation_id,
            )
        )

        return job

    def execute_campaign(
        self,
        campaign_id: int,
        *,
        actor: User,
    ) -> CampaignRemediationResult:
        campaign = self.validate_campaign(campaign_id)
        items = self._remediable_review_items(campaign.id)
        skipped_decisions = self._non_remediable_decision_count(campaign.id)
        jobs: list[RemediationJob] = []
        created_jobs = 0
        for item in items:
            existing_job = self._find_job_by_review_item(item.id)
            if existing_job is not None:
                jobs.append(existing_job)
                continue

            job = self.create_job(
                item.id,
                remediation_type=self._remediation_type_for_item(item),
                actor=actor,
            )
            created_jobs += 1
            jobs.append(self.execute_job(job, actor=actor))

        return CampaignRemediationResult(
            campaign_id=campaign.id,
            created_jobs=created_jobs,
            executed_jobs=created_jobs,
            skipped_decisions=skipped_decisions,
            jobs=jobs,
        )

    def validate_campaign(self, campaign_id: int) -> CertificationCampaign:
        campaign = self.db.get(CertificationCampaign, campaign_id)
        if campaign is None:
            raise RemediationCampaignNotFoundError(campaign_id)
        if campaign.status != CampaignStatus.COMPLETED.value:
            raise InvalidRemediationCampaignStateError(campaign)

        return campaign

    def prevent_duplicate_jobs(self, review_item_id: int) -> None:
        if self._find_job_by_review_item(review_item_id) is not None:
            raise DuplicateRemediationJobError(review_item_id)

    def lookup_job(self, job_id: int) -> RemediationJob:
        job = self.db.scalar(
            _remediation_job_query().where(RemediationJob.id == job_id)
        )
        if job is None:
            raise RemediationJobNotFoundError(job_id)

        return job

    def list_jobs(
        self,
        *,
        filters: RemediationJobFilters,
        offset: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: Literal["ascending", "descending"] | str = "descending",
    ) -> list[RemediationJob]:
        statement = _remediation_job_query()
        if filters.campaign_id is not None:
            statement = statement.where(RemediationJob.campaign_id == filters.campaign_id)
        if filters.review_item_id is not None:
            statement = statement.where(
                RemediationJob.review_item_id == filters.review_item_id
            )
        if filters.status is not None:
            statement = statement.where(RemediationJob.status == filters.status)
        if filters.remediation_type is not None:
            statement = statement.where(
                RemediationJob.remediation_type == filters.remediation_type
            )
        if filters.correlation_id is not None:
            statement = statement.where(
                RemediationJob.correlation_id == filters.correlation_id
            )

        statement = _apply_sorting(
            statement,
            sort_fields=SUPPORTED_REMEDIATION_JOB_SORT_FIELDS,
            sort_by=sort_by or "created_at",
            sort_order=sort_order,
        )

        return list(
            self.db.execute(statement.offset(offset).limit(limit))
            .unique()
            .scalars()
            .all()
        )

    def publish_pending_events(self) -> None:
        publish_domain_events(self.pending_events)
        self.pending_events.clear()

    def _lookup_review_item(self, review_item_id: int) -> CertificationReviewItem:
        item = self.db.scalar(
            select(CertificationReviewItem)
            .options(
                joinedload(CertificationReviewItem.campaign),
                joinedload(CertificationReviewItem.user),
                joinedload(CertificationReviewItem.application),
                joinedload(CertificationReviewItem.entitlement),
                joinedload(CertificationReviewItem.decision_record),
            )
            .where(CertificationReviewItem.id == review_item_id)
        )
        if item is None:
            raise RemediationReviewItemNotFoundError(review_item_id)

        return item

    def _find_job_by_review_item(
        self,
        review_item_id: int,
    ) -> RemediationJob | None:
        return self.db.scalar(
            _remediation_job_query().where(
                RemediationJob.review_item_id == review_item_id
            )
        )

    def _remediable_review_items(
        self,
        campaign_id: int,
    ) -> list[CertificationReviewItem]:
        return list(
            self.db.scalars(
                select(CertificationReviewItem)
                .join(CertificationDecision)
                .options(
                    joinedload(CertificationReviewItem.campaign),
                    joinedload(CertificationReviewItem.user),
                    joinedload(CertificationReviewItem.application),
                    joinedload(CertificationReviewItem.entitlement),
                    joinedload(CertificationReviewItem.decision_record),
                )
                .where(
                    CertificationReviewItem.campaign_id == campaign_id,
                    CertificationDecision.decision
                    == CertificationDecisionValue.REVOKE.value,
                )
                .order_by(CertificationReviewItem.id)
            ).all()
        )

    def _non_remediable_decision_count(self, campaign_id: int) -> int:
        return self.db.scalar(
            select(func.count(CertificationDecision.id))
            .where(
                CertificationDecision.campaign_id == campaign_id,
                CertificationDecision.decision
                != CertificationDecisionValue.REVOKE.value,
            )
        ) or 0

    def _remediation_type_for_item(
        self,
        item: CertificationReviewItem,
    ) -> RemediationType:
        if item.group_id is not None:
            return RemediationType.REMOVE_GROUP_MEMBER

        return RemediationType.REVOKE_ENTITLEMENT

    def _operation_for_job(
        self,
        job: RemediationJob,
        item: CertificationReviewItem,
    ) -> tuple[str, ConnectorOperation, dict[str, object]]:
        try:
            connector_name = connector_name_for_application(item.application.slug)
        except ValueError as exc:
            raise UnsupportedRemediationConnectorError(item.application.slug) from exc

        remediation_type = RemediationType(job.remediation_type)
        if remediation_type == RemediationType.REVOKE_ENTITLEMENT:
            return (
                connector_name,
                ConnectorOperation.REVOKE_ENTITLEMENT,
                {
                    "user_id": str(item.user_id),
                    "entitlement": _entitlement_payload(item.entitlement),
                },
            )
        if remediation_type == RemediationType.REMOVE_GROUP_MEMBER:
            if item.group_id is None:
                raise ValueError("Review item does not reference a group")
            return (
                connector_name,
                ConnectorOperation.REMOVE_GROUP_MEMBER,
                {
                    "group_id": str(item.group_id),
                    "user_id": str(item.user_id),
                },
            )
        if remediation_type == RemediationType.DISABLE_USER:
            return (
                connector_name,
                ConnectorOperation.DISABLE_USER,
                {"user_id": str(item.user_id)},
            )

        raise ValueError(f"Unsupported remediation type: {remediation_type.value}")

    def _link_provisioning_job(self, job: RemediationJob) -> None:
        provisioning_job = self.db.scalar(
            select(ProvisioningJob)
            .where(ProvisioningJob.correlation_id == job.correlation_id)
            .order_by(ProvisioningJob.id.desc())
        )
        if provisioning_job is not None:
            job.provisioning_job_id = provisioning_job.id
            self.db.flush()

    def _record_job_audit(
        self,
        job: RemediationJob,
        *,
        actor: User,
        action: str,
        result: str,
        reason: str,
    ) -> None:
        item = self._lookup_review_item(job.review_item_id)
        create_audit_event(
            self.db,
            requester_id=actor.id,
            target_user_id=item.user_id,
            action=action,
            application_id=item.application_id,
            entitlement_id=item.entitlement_id,
            result=result,
            reason=reason,
            correlation_id=job.correlation_id,
        )


def _remediation_job_query() -> Select[tuple[RemediationJob]]:
    return select(RemediationJob).options(
        joinedload(RemediationJob.campaign),
        joinedload(RemediationJob.review_item),
        joinedload(RemediationJob.provisioning_job),
        joinedload(RemediationJob.initiator),
    )


def _apply_sorting(
    statement: Select[Any],
    *,
    sort_fields: dict[str, ColumnElement[Any]],
    sort_by: str,
    sort_order: str,
) -> Select[Any]:
    if sort_order not in SUPPORTED_SORT_ORDERS:
        raise UnsupportedRemediationSortOrderError(sort_order)

    sort_expression = sort_fields.get(sort_by)
    if sort_expression is None:
        raise UnsupportedRemediationSortFieldError(sort_by)

    if sort_order == "descending":
        return statement.order_by(sort_expression.desc(), RemediationJob.id.desc())

    return statement.order_by(sort_expression.asc(), RemediationJob.id.asc())


def _entitlement_payload(entitlement: Entitlement) -> dict[str, object]:
    return {
        "id": entitlement.id,
        "slug": entitlement.slug,
        "name": entitlement.name,
        "application_id": entitlement.application_id,
    }


def _utc_now() -> datetime:
    return datetime.now(UTC)
