from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from ..domain.events import (
    DomainEvent,
    ProvisioningJobCompleted,
    ProvisioningJobCreated,
    ProvisioningJobFailed,
    ProvisioningJobStarted,
    ProvisioningRetryRecorded,
    event_time,
)
from ..domain.publisher import publish_domain_events
from ..models import ProvisioningHistory, ProvisioningJob


class ProvisioningJobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYABLE = "RETRYABLE"
    SKIPPED = "SKIPPED"


class ProvisioningHistoryEventType(StrEnum):
    JOB_CREATED = "job_created"
    JOB_STARTED = "job_started"
    CONNECTOR_INVOCATION = "connector_invocation"
    CONNECTOR_RESULT = "connector_result"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    RETRY_RECORDED = "retry_recorded"


SUPPORTED_PROVISIONING_JOB_SORT_FIELDS = {
    "id": ProvisioningJob.id,
    "created_at": ProvisioningJob.created_at,
    "started_at": ProvisioningJob.started_at,
    "completed_at": ProvisioningJob.completed_at,
    "connector": ProvisioningJob.connector,
    "operation": ProvisioningJob.operation,
    "status": ProvisioningJob.status,
}
SUPPORTED_PROVISIONING_HISTORY_SORT_FIELDS = {
    "id": ProvisioningHistory.id,
    "created_at": ProvisioningHistory.created_at,
    "connector": ProvisioningHistory.connector,
    "operation": ProvisioningHistory.operation,
    "event_type": ProvisioningHistory.event_type,
    "status": ProvisioningHistory.status,
}
SUPPORTED_SORT_ORDERS = {"ascending", "descending"}


@dataclass(frozen=True)
class ProvisioningJobFilters:
    connector: str | None = None
    operation: str | None = None
    status: str | None = None
    correlation_id: str | None = None
    target_type: str | None = None
    target_id: str | None = None


@dataclass(frozen=True)
class ProvisioningHistoryFilters:
    job_id: int | None = None
    connector: str | None = None
    operation: str | None = None
    event_type: str | None = None
    status: str | None = None
    correlation_id: str | None = None


class ProvisioningJobServiceError(Exception):
    """Base exception for provisioning job service failures."""


class ProvisioningJobNotFoundError(ProvisioningJobServiceError):
    def __init__(self, job_id: int) -> None:
        super().__init__(f"Provisioning job {job_id} was not found")
        self.job_id = job_id


class UnsupportedProvisioningSortFieldError(ProvisioningJobServiceError):
    def __init__(self, sort_by: str) -> None:
        super().__init__(f"Unsupported provisioning sort field: {sort_by}")
        self.sort_by = sort_by


class UnsupportedProvisioningSortOrderError(ProvisioningJobServiceError):
    def __init__(self, sort_order: str) -> None:
        super().__init__(f"Unsupported provisioning sort order: {sort_order}")
        self.sort_order = sort_order


class ProvisioningJobService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.pending_events: list[DomainEvent] = []

    def create_job(
        self,
        *,
        correlation_id: str,
        connector: str,
        operation: str,
        target_type: str,
        target_id: str | None,
        max_attempts: int,
    ) -> ProvisioningJob:
        job = ProvisioningJob(
            correlation_id=correlation_id,
            connector=connector,
            operation=operation,
            target_type=target_type,
            target_id=target_id,
            status=ProvisioningJobStatus.PENDING.value,
            attempt_count=0,
            retry_count=0,
            max_attempts=max_attempts,
            retryable=False,
        )
        self.db.add(job)
        self.db.flush()
        self.record_history(
            job,
            event_type=ProvisioningHistoryEventType.JOB_CREATED,
            status=ProvisioningJobStatus.PENDING.value,
            message="Provisioning job created",
        )
        self.pending_events.append(
            ProvisioningJobCreated(
                occurred_at=event_time(),
                job_id=job.id,
                correlation_id=job.correlation_id,
                connector=job.connector,
                operation=job.operation,
            )
        )

        return job

    def start_job(self, job: ProvisioningJob, *, attempt: int) -> ProvisioningJob:
        if job.started_at is None:
            job.started_at = _utc_now()

        job.status = ProvisioningJobStatus.RUNNING.value
        job.attempt_count = max(job.attempt_count, attempt)
        self.db.flush()
        self.record_history(
            job,
            event_type=ProvisioningHistoryEventType.JOB_STARTED,
            status=ProvisioningJobStatus.RUNNING.value,
            message=f"Provisioning job started attempt {attempt}",
            attempt=attempt,
        )
        self.pending_events.append(
            ProvisioningJobStarted(
                occurred_at=event_time(),
                job_id=job.id,
                correlation_id=job.correlation_id,
                connector=job.connector,
                operation=job.operation,
            )
        )

        return job

    def complete_job(
        self,
        job: ProvisioningJob,
        *,
        status: str,
        message: str,
        attempt: int,
        duration_ms: float,
        retryable: bool,
        details: dict[str, Any] | None = None,
    ) -> ProvisioningJob:
        completed_at = _utc_now()
        job.status = status
        job.attempt_count = max(job.attempt_count, attempt)
        job.retryable = retryable
        job.last_error = None
        job.completed_at = completed_at
        job.duration_ms = duration_ms
        self.db.flush()
        self.record_history(
            job,
            event_type=ProvisioningHistoryEventType.CONNECTOR_RESULT,
            status=status,
            message=message,
            attempt=attempt,
            retryable=retryable,
            duration_ms=duration_ms,
            details=details,
        )
        self.record_history(
            job,
            event_type=ProvisioningHistoryEventType.JOB_COMPLETED,
            status=status,
            message="Provisioning job completed",
            attempt=attempt,
            retryable=retryable,
            duration_ms=duration_ms,
        )
        self.pending_events.append(
            ProvisioningJobCompleted(
                occurred_at=event_time(),
                job_id=job.id,
                correlation_id=job.correlation_id,
                connector=job.connector,
                operation=job.operation,
                status=job.status,
            )
        )

        return job

    def fail_job(
        self,
        job: ProvisioningJob,
        *,
        status: str,
        message: str,
        attempt: int,
        duration_ms: float,
        retryable: bool,
        details: dict[str, Any] | None = None,
    ) -> ProvisioningJob:
        job.status = status
        job.attempt_count = max(job.attempt_count, attempt)
        job.retryable = retryable
        job.last_error = message
        job.completed_at = _utc_now()
        job.duration_ms = duration_ms
        self.db.flush()
        self.record_history(
            job,
            event_type=ProvisioningHistoryEventType.CONNECTOR_RESULT,
            status=status,
            message=message,
            attempt=attempt,
            retryable=retryable,
            duration_ms=duration_ms,
            details=details,
        )
        self.record_history(
            job,
            event_type=ProvisioningHistoryEventType.JOB_FAILED,
            status=status,
            message="Provisioning job failed",
            attempt=attempt,
            retryable=retryable,
            duration_ms=duration_ms,
        )
        self.pending_events.append(
            ProvisioningJobFailed(
                occurred_at=event_time(),
                job_id=job.id,
                correlation_id=job.correlation_id,
                connector=job.connector,
                operation=job.operation,
                retryable=retryable,
                message=message,
            )
        )

        return job

    def record_retry(
        self,
        job: ProvisioningJob,
        *,
        attempt: int,
        next_attempt: int,
        delay_ms: int,
        reason: str,
    ) -> ProvisioningHistory:
        job.retry_count += 1
        job.attempt_count = max(job.attempt_count, attempt)
        job.retryable = True
        job.last_error = reason
        self.db.flush()
        history = self.record_history(
            job,
            event_type=ProvisioningHistoryEventType.RETRY_RECORDED,
            status=ProvisioningJobStatus.RETRYABLE.value,
            message=reason,
            attempt=attempt,
            retryable=True,
            details={
                "next_attempt": next_attempt,
                "delay_ms": delay_ms,
            },
        )
        self.pending_events.append(
            ProvisioningRetryRecorded(
                occurred_at=event_time(),
                job_id=job.id,
                correlation_id=job.correlation_id,
                connector=job.connector,
                operation=job.operation,
                attempt=attempt,
                next_attempt=next_attempt,
                delay_ms=delay_ms,
            )
        )

        return history

    def record_history(
        self,
        job: ProvisioningJob,
        *,
        event_type: ProvisioningHistoryEventType | str,
        status: str,
        message: str,
        attempt: int = 0,
        retryable: bool = False,
        duration_ms: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> ProvisioningHistory:
        history = ProvisioningHistory(
            job_id=job.id,
            correlation_id=job.correlation_id,
            connector=job.connector,
            operation=job.operation,
            event_type=str(event_type),
            status=status,
            message=message,
            attempt=attempt,
            retryable=retryable,
            duration_ms=duration_ms,
            details=_serialize_details(details),
        )
        self.db.add(history)
        self.db.flush()

        return history

    def lookup_job(self, job_id: int) -> ProvisioningJob:
        job = self.db.scalar(
            select(ProvisioningJob)
            .options(joinedload(ProvisioningJob.history_entries))
            .where(ProvisioningJob.id == job_id)
        )
        if job is None:
            raise ProvisioningJobNotFoundError(job_id)

        return job

    def list_jobs(
        self,
        *,
        filters: ProvisioningJobFilters,
        offset: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: Literal["ascending", "descending"] | str = "descending",
    ) -> list[ProvisioningJob]:
        statement = select(ProvisioningJob)
        statement = self._apply_job_filters(statement, filters)
        statement = self._apply_sorting(
            statement,
            sort_fields=SUPPORTED_PROVISIONING_JOB_SORT_FIELDS,
            sort_by=sort_by or "created_at",
            sort_order=sort_order,
        )

        return list(self.db.scalars(statement.offset(offset).limit(limit)).all())

    def list_history(
        self,
        *,
        filters: ProvisioningHistoryFilters,
        offset: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: Literal["ascending", "descending"] | str = "descending",
    ) -> list[ProvisioningHistory]:
        statement = select(ProvisioningHistory)
        statement = self._apply_history_filters(statement, filters)
        statement = self._apply_sorting(
            statement,
            sort_fields=SUPPORTED_PROVISIONING_HISTORY_SORT_FIELDS,
            sort_by=sort_by or "created_at",
            sort_order=sort_order,
        )

        return list(self.db.scalars(statement.offset(offset).limit(limit)).all())

    def publish_pending_events(self) -> None:
        publish_domain_events(self.pending_events)
        self.pending_events.clear()

    def _apply_job_filters(
        self,
        statement: Select[tuple[ProvisioningJob]],
        filters: ProvisioningJobFilters,
    ) -> Select[tuple[ProvisioningJob]]:
        if filters.connector is not None:
            statement = statement.where(ProvisioningJob.connector == filters.connector)
        if filters.operation is not None:
            statement = statement.where(ProvisioningJob.operation == filters.operation)
        if filters.status is not None:
            statement = statement.where(ProvisioningJob.status == filters.status)
        if filters.correlation_id is not None:
            statement = statement.where(
                ProvisioningJob.correlation_id == filters.correlation_id
            )
        if filters.target_type is not None:
            statement = statement.where(
                ProvisioningJob.target_type == filters.target_type
            )
        if filters.target_id is not None:
            statement = statement.where(ProvisioningJob.target_id == filters.target_id)

        return statement

    def _apply_history_filters(
        self,
        statement: Select[tuple[ProvisioningHistory]],
        filters: ProvisioningHistoryFilters,
    ) -> Select[tuple[ProvisioningHistory]]:
        if filters.job_id is not None:
            statement = statement.where(ProvisioningHistory.job_id == filters.job_id)
        if filters.connector is not None:
            statement = statement.where(
                ProvisioningHistory.connector == filters.connector
            )
        if filters.operation is not None:
            statement = statement.where(
                ProvisioningHistory.operation == filters.operation
            )
        if filters.event_type is not None:
            statement = statement.where(
                ProvisioningHistory.event_type == filters.event_type
            )
        if filters.status is not None:
            statement = statement.where(ProvisioningHistory.status == filters.status)
        if filters.correlation_id is not None:
            statement = statement.where(
                ProvisioningHistory.correlation_id == filters.correlation_id
            )

        return statement

    def _apply_sorting(
        self,
        statement: Select[Any],
        *,
        sort_fields: dict[str, Any],
        sort_by: str,
        sort_order: str,
    ) -> Select[Any]:
        if sort_order not in SUPPORTED_SORT_ORDERS:
            raise UnsupportedProvisioningSortOrderError(sort_order)

        sort_expression = sort_fields.get(sort_by)
        if sort_expression is None:
            raise UnsupportedProvisioningSortFieldError(sort_by)

        if sort_order == "descending":
            return statement.order_by(sort_expression.desc())

        return statement.order_by(sort_expression.asc())


def history_details_to_dict(history: ProvisioningHistory) -> dict[str, object]:
    if history.details is None:
        return {}

    try:
        details = json.loads(history.details)
    except json.JSONDecodeError:
        return {}

    if not isinstance(details, dict):
        return {}

    return details


def _serialize_details(details: dict[str, Any] | None) -> str | None:
    if details is None:
        return None

    return json.dumps(details, sort_keys=True, default=str)


def _utc_now() -> datetime:
    return datetime.now(UTC)
