from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql.elements import ColumnElement

from ..audit_service import create_audit_event
from ..domain.events import (
    CertificationCampaignCancelled,
    CertificationCampaignCompleted,
    CertificationCampaignCreated,
    CertificationCampaignStarted,
    CertificationDecisionRecorded,
    CertificationDecisionUpdated,
    DomainEvent,
    event_time,
)
from ..domain.publisher import publish_domain_events
from ..models import AccessAssignment, Application, Entitlement, User
from ..observability import metrics_registry
from .enums import CampaignStatus, CertificationDecisionValue, ReviewItemStatus
from .models import (
    CertificationCampaign,
    CertificationDecision,
    CertificationReviewItem,
)
from .validation import validate_campaign_transition

GOVERNANCE_AUDIT_APPLICATION_SLUG = "governance"
GOVERNANCE_AUDIT_ENTITLEMENT_SLUG = "access-review-certification"

ACTION_CAMPAIGN_CREATED = "certification_campaign_created"
ACTION_CAMPAIGN_STARTED = "certification_campaign_started"
ACTION_CAMPAIGN_CANCELLED = "certification_campaign_cancelled"
ACTION_CAMPAIGN_COMPLETED = "certification_campaign_completed"
ACTION_REVIEW_APPROVED = "certification_review_approved"
ACTION_REVIEW_REVOKED = "certification_review_revoked"
ACTION_REVIEW_ABSTAINED = "certification_review_abstained"
ACTION_DECISION_UPDATED = "certification_decision_updated"

SUPPORTED_CAMPAIGN_SORT_FIELDS: dict[str, ColumnElement[Any]] = {
    "id": CertificationCampaign.id,
    "name": func.lower(CertificationCampaign.name),
    "status": CertificationCampaign.status,
    "created_at": CertificationCampaign.created_at,
    "started_at": CertificationCampaign.started_at,
    "completed_at": CertificationCampaign.completed_at,
}
SUPPORTED_REVIEW_ITEM_SORT_FIELDS: dict[str, ColumnElement[Any]] = {
    "id": CertificationReviewItem.id,
    "status": CertificationReviewItem.status,
    "created_at": CertificationReviewItem.created_at,
    "reviewed_at": CertificationReviewItem.reviewed_at,
    "user_id": CertificationReviewItem.user_id,
    "application_id": CertificationReviewItem.application_id,
}
SUPPORTED_SORT_ORDERS = {"ascending", "descending"}


@dataclass(frozen=True)
class CampaignFilters:
    status: str | None = None
    created_by: int | None = None
    reviewer_id: int | None = None


@dataclass(frozen=True)
class ReviewItemFilters:
    status: str | None = None
    reviewer_id: int | None = None
    decision: str | None = None


class GovernanceServiceError(Exception):
    """Base exception for governance service failures."""


class DuplicateCampaignNameError(GovernanceServiceError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Certification campaign {name!r} already exists")
        self.name = name


class CampaignNotFoundError(GovernanceServiceError):
    def __init__(self, campaign_id: int) -> None:
        super().__init__(f"Certification campaign {campaign_id} was not found")
        self.campaign_id = campaign_id


class ReviewItemNotFoundError(GovernanceServiceError):
    def __init__(self, item_id: int) -> None:
        super().__init__(f"Certification review item {item_id} was not found")
        self.item_id = item_id


class MissingReviewerError(GovernanceServiceError):
    def __init__(self, reviewer_id: int) -> None:
        super().__init__(f"Reviewer {reviewer_id} was not found")
        self.reviewer_id = reviewer_id


class InvalidCampaignTransitionError(GovernanceServiceError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class IncompleteCampaignError(GovernanceServiceError):
    def __init__(self, campaign: CertificationCampaign) -> None:
        super().__init__(
            "Campaign cannot be completed while review items are pending"
        )
        self.campaign = campaign


class UnsupportedGovernanceSortFieldError(GovernanceServiceError):
    def __init__(self, sort_by: str) -> None:
        super().__init__(f"Unsupported governance sort field: {sort_by}")
        self.sort_by = sort_by


class UnsupportedGovernanceSortOrderError(GovernanceServiceError):
    def __init__(self, sort_order: str) -> None:
        super().__init__(f"Unsupported governance sort order: {sort_order}")
        self.sort_order = sort_order


class CampaignService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.pending_events: list[DomainEvent] = []

    def create_campaign(
        self,
        *,
        name: str,
        description: str | None,
        reviewer_id: int,
        actor: User,
    ) -> CertificationCampaign:
        self._check_duplicate_campaign_name(name)
        reviewer = self.db.get(User, reviewer_id)
        if reviewer is None:
            raise MissingReviewerError(reviewer_id)

        campaign = CertificationCampaign(
            name=name.strip(),
            description=_normalize_optional_text(description),
            status=CampaignStatus.DRAFT.value,
            created_by=actor.id,
            default_reviewer_id=reviewer.id,
        )
        self.db.add(campaign)
        self.db.flush()
        self._record_governance_audit(
            actor=actor,
            target_user_id=actor.id,
            action=ACTION_CAMPAIGN_CREATED,
            result="succeeded",
            reason=f"Certification campaign {campaign.id} created",
        )
        self.pending_events.append(
            CertificationCampaignCreated(
                occurred_at=event_time(),
                campaign_id=campaign.id,
                name=campaign.name,
            )
        )

        return campaign

    def generate_review_items(
        self,
        campaign: CertificationCampaign,
    ) -> list[CertificationReviewItem]:
        existing_count = self.db.scalar(
            select(func.count(CertificationReviewItem.id)).where(
                CertificationReviewItem.campaign_id == campaign.id
            )
        )
        if existing_count:
            return list(campaign.review_items)

        assignments = self.db.scalars(
            select(AccessAssignment)
            .options(joinedload(AccessAssignment.entitlement))
            .order_by(AccessAssignment.id)
        ).all()
        items: list[CertificationReviewItem] = []
        for assignment in assignments:
            item = CertificationReviewItem(
                campaign_id=campaign.id,
                access_assignment_id=assignment.id,
                user_id=assignment.user_id,
                application_id=assignment.entitlement.application_id,
                entitlement_id=assignment.entitlement_id,
                reviewer_id=campaign.default_reviewer_id,
                status=ReviewItemStatus.PENDING.value,
            )
            self.db.add(item)
            items.append(item)

        self.db.flush()
        self._recalculate_campaign_counts(campaign)

        return items

    def start_campaign(
        self,
        campaign_id: int,
        *,
        actor: User,
    ) -> CertificationCampaign:
        campaign = self.lookup_campaign(campaign_id)
        self._validate_transition(campaign, CampaignStatus.ACTIVE)
        self.generate_review_items(campaign)
        campaign.status = CampaignStatus.ACTIVE.value
        campaign.started_at = _utc_now()
        self.db.flush()
        self._record_governance_audit(
            actor=actor,
            target_user_id=actor.id,
            action=ACTION_CAMPAIGN_STARTED,
            result="succeeded",
            reason=(
                f"Certification campaign {campaign.id} started with "
                f"{campaign.total_items} review items"
            ),
        )
        self.pending_events.append(
            CertificationCampaignStarted(
                occurred_at=event_time(),
                campaign_id=campaign.id,
                total_items=campaign.total_items,
            )
        )

        return campaign

    def complete_campaign(
        self,
        campaign_id: int,
        *,
        actor: User,
    ) -> CertificationCampaign:
        campaign = self.lookup_campaign(campaign_id)
        self._validate_transition(campaign, CampaignStatus.COMPLETED)
        self._recalculate_campaign_counts(campaign)
        if campaign.completed_items < campaign.total_items:
            raise IncompleteCampaignError(campaign)

        campaign.status = CampaignStatus.COMPLETED.value
        campaign.completed_at = _utc_now()
        self.db.flush()
        self._record_governance_audit(
            actor=actor,
            target_user_id=actor.id,
            action=ACTION_CAMPAIGN_COMPLETED,
            result="succeeded",
            reason=f"Certification campaign {campaign.id} completed",
        )
        self.pending_events.append(
            CertificationCampaignCompleted(
                occurred_at=event_time(),
                campaign_id=campaign.id,
                approval_count=campaign.approval_count,
                revocation_count=campaign.revocation_count,
                abstain_count=campaign.abstain_count,
            )
        )

        return campaign

    def cancel_campaign(
        self,
        campaign_id: int,
        *,
        actor: User,
    ) -> CertificationCampaign:
        campaign = self.lookup_campaign(campaign_id)
        self._validate_transition(campaign, CampaignStatus.CANCELLED)
        campaign.status = CampaignStatus.CANCELLED.value
        campaign.cancelled_at = _utc_now()
        self.db.flush()
        self._record_governance_audit(
            actor=actor,
            target_user_id=actor.id,
            action=ACTION_CAMPAIGN_CANCELLED,
            result="succeeded",
            reason=f"Certification campaign {campaign.id} cancelled",
        )
        self.pending_events.append(
            CertificationCampaignCancelled(
                occurred_at=event_time(),
                campaign_id=campaign.id,
            )
        )

        return campaign

    def lookup_campaign(self, campaign_id: int) -> CertificationCampaign:
        campaign = self.db.scalar(
            select(CertificationCampaign)
            .options(
                joinedload(CertificationCampaign.creator),
                joinedload(CertificationCampaign.default_reviewer),
            )
            .where(CertificationCampaign.id == campaign_id)
        )
        if campaign is None:
            raise CampaignNotFoundError(campaign_id)

        return campaign

    def list_campaigns(
        self,
        *,
        filters: CampaignFilters,
        offset: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: Literal["ascending", "descending"] | str = "descending",
    ) -> list[CertificationCampaign]:
        statement = select(CertificationCampaign)
        if filters.status is not None:
            statement = statement.where(CertificationCampaign.status == filters.status)
        if filters.created_by is not None:
            statement = statement.where(
                CertificationCampaign.created_by == filters.created_by
            )
        if filters.reviewer_id is not None:
            statement = statement.where(
                CertificationCampaign.default_reviewer_id == filters.reviewer_id
            )

        statement = _apply_sorting(
            statement,
            sort_fields=SUPPORTED_CAMPAIGN_SORT_FIELDS,
            sort_by=sort_by or "created_at",
            sort_order=sort_order,
        )

        return list(self.db.scalars(statement.offset(offset).limit(limit)).all())

    def summarize_campaign(
        self,
        campaign_id: int,
    ) -> CertificationCampaign:
        campaign = self.lookup_campaign(campaign_id)
        self._recalculate_campaign_counts(campaign)

        return campaign

    def publish_pending_events(self) -> None:
        publish_domain_events(self.pending_events)
        self.pending_events.clear()

    def _check_duplicate_campaign_name(self, name: str) -> None:
        existing = self.db.scalar(
            select(CertificationCampaign).where(
                func.lower(CertificationCampaign.name) == name.strip().lower()
            )
        )
        if existing is not None:
            raise DuplicateCampaignNameError(name)

    def _validate_transition(
        self,
        campaign: CertificationCampaign,
        next_status: CampaignStatus,
    ) -> None:
        try:
            validate_campaign_transition(campaign.status, next_status)
        except ValueError as exc:
            raise InvalidCampaignTransitionError(str(exc)) from exc

    def _recalculate_campaign_counts(
        self,
        campaign: CertificationCampaign,
    ) -> None:
        self.db.flush()
        total_items = self.db.scalar(
            select(func.count(CertificationReviewItem.id)).where(
                CertificationReviewItem.campaign_id == campaign.id
            )
        )
        completed_items = self.db.scalar(
            select(func.count(CertificationReviewItem.id)).where(
                CertificationReviewItem.campaign_id == campaign.id,
                CertificationReviewItem.status == ReviewItemStatus.COMPLETED.value,
            )
        )
        decision_counts = {
            decision: count
            for decision, count in self.db.execute(
                select(CertificationDecision.decision, func.count())
                .where(CertificationDecision.campaign_id == campaign.id)
                .group_by(CertificationDecision.decision)
            ).all()
        }
        campaign.total_items = total_items or 0
        campaign.completed_items = completed_items or 0
        campaign.approval_count = decision_counts.get(
            CertificationDecisionValue.APPROVE.value,
            0,
        )
        campaign.revocation_count = decision_counts.get(
            CertificationDecisionValue.REVOKE.value,
            0,
        )
        campaign.abstain_count = decision_counts.get(
            CertificationDecisionValue.ABSTAIN.value,
            0,
        )
        self.db.flush()

    def _record_governance_audit(
        self,
        *,
        actor: User,
        target_user_id: int,
        action: str,
        result: str,
        reason: str,
    ) -> None:
        entitlement = get_governance_audit_entitlement(self.db)
        create_audit_event(
            self.db,
            requester_id=actor.id,
            target_user_id=target_user_id,
            action=action,
            application_id=entitlement.application_id,
            entitlement_id=entitlement.id,
            result=result,
            reason=reason,
        )


class ReviewService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.pending_events: list[DomainEvent] = []

    def lookup_review_item(self, item_id: int) -> CertificationReviewItem:
        item = self.db.scalar(
            _review_item_query().where(CertificationReviewItem.id == item_id)
        )
        if item is None:
            raise ReviewItemNotFoundError(item_id)

        return item

    def list_review_items(
        self,
        campaign_id: int,
        *,
        filters: ReviewItemFilters,
        offset: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: Literal["ascending", "descending"] | str = "ascending",
    ) -> list[CertificationReviewItem]:
        campaign = self.db.get(CertificationCampaign, campaign_id)
        if campaign is None:
            raise CampaignNotFoundError(campaign_id)

        statement = _review_item_query().where(
            CertificationReviewItem.campaign_id == campaign_id
        )
        if filters.status is not None:
            statement = statement.where(CertificationReviewItem.status == filters.status)
        if filters.reviewer_id is not None:
            statement = statement.where(
                CertificationReviewItem.reviewer_id == filters.reviewer_id
            )
        if filters.decision is not None:
            statement = statement.join(CertificationDecision).where(
                CertificationDecision.decision == filters.decision
            )

        statement = _apply_sorting(
            statement,
            sort_fields=SUPPORTED_REVIEW_ITEM_SORT_FIELDS,
            sort_by=sort_by or "id",
            sort_order=sort_order,
        )

        return list(
            self.db.execute(statement.offset(offset).limit(limit))
            .unique()
            .scalars()
            .all()
        )

    def record_decision(
        self,
        item_id: int,
        *,
        decision: CertificationDecisionValue,
        comments: str | None,
        actor: User,
    ) -> CertificationReviewItem:
        item = self.lookup_review_item(item_id)
        campaign = item.campaign
        if campaign.status != CampaignStatus.ACTIVE.value:
            raise InvalidCampaignTransitionError(
                "Decisions can only be recorded for active campaigns"
            )

        now = _utc_now()
        normalized_comments = _normalize_optional_text(comments)
        existing_decision = item.decision_record
        previous_decision = (
            CertificationDecisionValue(existing_decision.decision)
            if existing_decision is not None
            else None
        )
        if existing_decision is None:
            item.decision_record = CertificationDecision(
                campaign_id=campaign.id,
                review_item_id=item.id,
                reviewer_id=actor.id,
                decision=decision.value,
                comments=normalized_comments,
            )
            self.pending_events.append(
                CertificationDecisionRecorded(
                    occurred_at=event_time(),
                    campaign_id=campaign.id,
                    review_item_id=item.id,
                    reviewer_id=actor.id,
                    user_id=item.user_id,
                    entitlement_id=item.entitlement_id,
                    decision=decision.value,
                )
            )
            audit_action = _decision_audit_action(decision)
            audit_reason = f"Review item {item.id} recorded as {decision.value}"
        else:
            existing_decision.reviewer_id = actor.id
            existing_decision.decision = decision.value
            existing_decision.comments = normalized_comments
            existing_decision.updated_at = now
            self.pending_events.append(
                CertificationDecisionUpdated(
                    occurred_at=event_time(),
                    campaign_id=campaign.id,
                    review_item_id=item.id,
                    reviewer_id=actor.id,
                    user_id=item.user_id,
                    entitlement_id=item.entitlement_id,
                    previous_decision=previous_decision.value
                    if previous_decision is not None
                    else None,
                    decision=decision.value,
                )
            )
            audit_action = ACTION_DECISION_UPDATED
            audit_reason = (
                f"Review item {item.id} updated from "
                f"{previous_decision.value if previous_decision else 'NONE'} "
                f"to {decision.value}"
            )

        item.status = ReviewItemStatus.COMPLETED.value
        item.reviewer_id = actor.id
        item.reviewed_at = now
        self.db.flush()
        CampaignService(self.db)._recalculate_campaign_counts(campaign)
        self._record_decision_audit(
            actor=actor,
            item=item,
            action=audit_action,
            reason=audit_reason,
        )
        metrics_registry.increment("review_decisions_total")

        return self.lookup_review_item(item_id)

    def publish_pending_events(self) -> None:
        publish_domain_events(self.pending_events)
        self.pending_events.clear()

    def _record_decision_audit(
        self,
        *,
        actor: User,
        item: CertificationReviewItem,
        action: str,
        reason: str,
    ) -> None:
        create_audit_event(
            self.db,
            requester_id=actor.id,
            target_user_id=item.user_id,
            action=action,
            application_id=item.application_id,
            entitlement_id=item.entitlement_id,
            result="succeeded",
            reason=reason,
        )


def get_governance_audit_entitlement(db: Session) -> Entitlement:
    entitlement = db.scalar(
        select(Entitlement)
        .join(Application)
        .where(
            Application.slug == GOVERNANCE_AUDIT_APPLICATION_SLUG,
            Entitlement.slug == GOVERNANCE_AUDIT_ENTITLEMENT_SLUG,
        )
    )
    if entitlement is None:
        raise RuntimeError("Governance audit entitlement is not seeded")

    return entitlement


def campaign_completion_percentage(campaign: CertificationCampaign) -> float:
    if campaign.total_items == 0:
        return 0.0

    return round((campaign.completed_items / campaign.total_items) * 100, 2)


def _review_item_query() -> Select[tuple[CertificationReviewItem]]:
    return select(CertificationReviewItem).options(
        joinedload(CertificationReviewItem.campaign),
        joinedload(CertificationReviewItem.user),
        joinedload(CertificationReviewItem.application),
        joinedload(CertificationReviewItem.entitlement),
        joinedload(CertificationReviewItem.reviewer),
        joinedload(CertificationReviewItem.decision_record),
    )


def _apply_sorting(
    statement: Select[Any],
    *,
    sort_fields: dict[str, ColumnElement[Any]],
    sort_by: str,
    sort_order: str,
) -> Select[Any]:
    if sort_order not in SUPPORTED_SORT_ORDERS:
        raise UnsupportedGovernanceSortOrderError(sort_order)

    sort_expression = sort_fields.get(sort_by)
    if sort_expression is None:
        raise UnsupportedGovernanceSortFieldError(sort_by)

    if sort_order == "descending":
        return statement.order_by(sort_expression.desc())

    return statement.order_by(sort_expression.asc())


def _decision_audit_action(decision: CertificationDecisionValue) -> str:
    if decision == CertificationDecisionValue.APPROVE:
        return ACTION_REVIEW_APPROVED
    if decision == CertificationDecisionValue.REVOKE:
        return ACTION_REVIEW_REVOKED

    return ACTION_REVIEW_ABSTAINED


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    if normalized == "":
        return None

    return normalized


def _utc_now() -> datetime:
    return datetime.now(UTC)
