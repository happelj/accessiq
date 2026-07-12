from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class DomainEvent:
    occurred_at: datetime


@dataclass(frozen=True)
class GroupCreated(DomainEvent):
    group_id: int
    display_name: str


@dataclass(frozen=True)
class GroupUpdated(DomainEvent):
    group_id: int
    display_name: str


@dataclass(frozen=True)
class GroupMembershipAdded(DomainEvent):
    group_id: int
    user_id: int


@dataclass(frozen=True)
class GroupMembershipRemoved(DomainEvent):
    group_id: int
    user_id: int


@dataclass(frozen=True)
class GroupMembershipReplaced(DomainEvent):
    group_id: int
    user_ids: tuple[int, ...]


@dataclass(frozen=True)
class UserProvisioned(DomainEvent):
    user_id: int
    user_name: str


@dataclass(frozen=True)
class EnterpriseProfileCreated(DomainEvent):
    user_id: int


@dataclass(frozen=True)
class EnterpriseProfileUpdated(DomainEvent):
    user_id: int


@dataclass(frozen=True)
class ManagerChanged(DomainEvent):
    user_id: int
    manager_id: int | None


@dataclass(frozen=True)
class DepartmentChanged(DomainEvent):
    user_id: int
    department: str | None


@dataclass(frozen=True)
class OrganizationChanged(DomainEvent):
    user_id: int
    organization: str | None


@dataclass(frozen=True)
class CostCenterChanged(DomainEvent):
    user_id: int
    cost_center: str | None


@dataclass(frozen=True)
class DivisionChanged(DomainEvent):
    user_id: int
    division: str | None


@dataclass(frozen=True)
class EmployeeNumberChanged(DomainEvent):
    user_id: int
    employee_number: str | None


@dataclass(frozen=True)
class ProvisioningStarted(DomainEvent):
    connector: str
    operation: str
    correlation_id: str


@dataclass(frozen=True)
class ProvisioningCompleted(DomainEvent):
    connector: str
    operation: str
    correlation_id: str
    status: str


@dataclass(frozen=True)
class ProvisioningFailed(DomainEvent):
    connector: str
    operation: str
    correlation_id: str
    message: str


@dataclass(frozen=True)
class ConnectorCalled(DomainEvent):
    connector: str
    operation: str
    correlation_id: str
    attempt: int


@dataclass(frozen=True)
class ConnectorSucceeded(DomainEvent):
    connector: str
    operation: str
    correlation_id: str
    attempt: int
    duration_ms: float


@dataclass(frozen=True)
class ConnectorFailed(DomainEvent):
    connector: str
    operation: str
    correlation_id: str
    attempt: int
    retryable: bool
    message: str


@dataclass(frozen=True)
class ConnectorRetryScheduled(DomainEvent):
    connector: str
    operation: str
    correlation_id: str
    attempt: int
    next_attempt: int
    delay_ms: int
    reason: str


@dataclass(frozen=True)
class ProvisioningJobCreated(DomainEvent):
    job_id: int
    correlation_id: str
    connector: str
    operation: str


@dataclass(frozen=True)
class ProvisioningJobStarted(DomainEvent):
    job_id: int
    correlation_id: str
    connector: str
    operation: str


@dataclass(frozen=True)
class ProvisioningJobCompleted(DomainEvent):
    job_id: int
    correlation_id: str
    connector: str
    operation: str
    status: str


@dataclass(frozen=True)
class ProvisioningJobFailed(DomainEvent):
    job_id: int
    correlation_id: str
    connector: str
    operation: str
    retryable: bool
    message: str


@dataclass(frozen=True)
class ProvisioningRetryRecorded(DomainEvent):
    job_id: int
    correlation_id: str
    connector: str
    operation: str
    attempt: int
    next_attempt: int
    delay_ms: int


@dataclass(frozen=True)
class CertificationCampaignCreated(DomainEvent):
    campaign_id: int
    name: str


@dataclass(frozen=True)
class CertificationCampaignStarted(DomainEvent):
    campaign_id: int
    total_items: int


@dataclass(frozen=True)
class CertificationCampaignCompleted(DomainEvent):
    campaign_id: int
    approval_count: int
    revocation_count: int
    abstain_count: int


@dataclass(frozen=True)
class CertificationCampaignCancelled(DomainEvent):
    campaign_id: int


@dataclass(frozen=True)
class CertificationDecisionRecorded(DomainEvent):
    campaign_id: int
    review_item_id: int
    reviewer_id: int
    user_id: int
    entitlement_id: int
    decision: str


@dataclass(frozen=True)
class CertificationDecisionUpdated(DomainEvent):
    campaign_id: int
    review_item_id: int
    reviewer_id: int
    user_id: int
    entitlement_id: int
    previous_decision: str | None
    decision: str


def event_time() -> datetime:
    return datetime.now(UTC)
