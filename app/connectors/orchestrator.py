from __future__ import annotations

from collections.abc import Mapping
from time import perf_counter
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit_service import create_audit_event
from ..domain.events import (
    ConnectorCalled,
    ConnectorFailed,
    ConnectorRetryScheduled,
    ConnectorSucceeded,
    DomainEvent,
    ProvisioningCompleted,
    ProvisioningFailed,
    ProvisioningStarted,
    event_time,
)
from ..domain.publisher import publish_domain_events
from ..models import Application, Entitlement
from ..observability import log_event, metrics_registry
from ..request_context import get_request_context
from ..services.provisioning_job_service import (
    ProvisioningHistoryEventType,
    ProvisioningJobService,
    ProvisioningJobStatus,
)
from .base import IdentityConnector
from .exceptions import ValidationError
from .registry import ConnectorRegistry
from .results import ConnectorOperation, ConnectorResult
from .retry import RetryPolicy

CONNECTOR_AUDIT_APPLICATION_SLUG = "connector-framework"
CONNECTOR_AUDIT_ENTITLEMENT_SLUG = "connector-execution"

ACTION_CONNECTOR_INVOCATION = "connector_invocation"
ACTION_CONNECTOR_SUCCESS = "connector_success"
ACTION_CONNECTOR_FAILURE = "connector_failure"
ACTION_CONNECTOR_RETRY_SCHEDULED = "connector_retry_scheduled"
ACTION_PROVISIONING_COMPLETED = "connector_provisioning_completed"
ACTION_PROVISIONING_JOB_CREATED = "provisioning_job_created"
ACTION_PROVISIONING_JOB_COMPLETED = "provisioning_job_completed"
ACTION_PROVISIONING_JOB_FAILED = "provisioning_job_failed"
ACTION_PROVISIONING_RETRY_RECORDED = "provisioning_retry_recorded"


class ProvisioningOrchestrator:
    def __init__(
        self,
        *,
        registry: ConnectorRegistry,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.registry = registry
        self.retry_policy = retry_policy or RetryPolicy()

    def execute(
        self,
        *,
        connector_name: str,
        operation: ConnectorOperation | str,
        payload: Mapping[str, Any] | None = None,
        correlation_id: str | None = None,
        db: Session | None = None,
        requester_id: int | None = None,
        target_user_id: int | None = None,
    ) -> ConnectorResult:
        resolved_operation = ConnectorOperation(operation)
        context = get_request_context()
        resolved_correlation_id = (
            correlation_id
            or (context.correlation_id if context is not None else None)
            or str(uuid4())
        )
        connector = self.registry.get(connector_name)
        operation_payload = dict(payload or {})
        job_service = ProvisioningJobService(db) if db is not None else None
        job = None
        if job_service is not None:
            job = job_service.create_job(
                correlation_id=resolved_correlation_id,
                connector=connector.name,
                operation=resolved_operation.value,
                target_type=_infer_target_type(resolved_operation),
                target_id=_infer_target_id(resolved_operation, operation_payload),
                max_attempts=self.retry_policy.max_attempts,
            )
            self._record_audit(
                db,
                requester_id=requester_id,
                target_user_id=target_user_id,
                action=ACTION_PROVISIONING_JOB_CREATED,
                result="succeeded",
                reason=(
                    f"Provisioning job {job.id} created for "
                    f"{connector.name} {resolved_operation.value}"
                ),
                correlation_id=resolved_correlation_id,
            )
        events: list[DomainEvent] = [
            ProvisioningStarted(
                occurred_at=event_time(),
                connector=connector.name,
                operation=resolved_operation.value,
                correlation_id=resolved_correlation_id,
            )
        ]
        attempt = 1
        started_at = perf_counter()

        while True:
            if job_service is not None and job is not None:
                job_service.start_job(job, attempt=attempt)
                job_service.record_history(
                    job,
                    event_type=ProvisioningHistoryEventType.CONNECTOR_INVOCATION,
                    status=ProvisioningJobStatus.RUNNING.value,
                    message=(
                        f"Connector {connector.name} called for "
                        f"{resolved_operation.value}"
                    ),
                    attempt=attempt,
                )
            events.append(
                ConnectorCalled(
                    occurred_at=event_time(),
                    connector=connector.name,
                    operation=resolved_operation.value,
                    correlation_id=resolved_correlation_id,
                    attempt=attempt,
                )
            )
            metrics_registry.increment("connector_invocations_total")
            self._record_audit(
                db,
                requester_id=requester_id,
                target_user_id=target_user_id,
                action=ACTION_CONNECTOR_INVOCATION,
                result="succeeded",
                reason=(
                    f"Connector {connector.name} called for "
                    f"{resolved_operation.value}"
                ),
                correlation_id=resolved_correlation_id,
            )

            try:
                result = self._call_connector(
                    connector,
                    resolved_operation,
                    operation_payload,
                    correlation_id=resolved_correlation_id,
                )
            except Exception as exc:
                decision = self.retry_policy.decision(exc, attempt=attempt)

                if decision.should_retry:
                    metrics_registry.increment("connector_retries_total")
                    if job_service is not None and job is not None:
                        job_service.record_retry(
                            job,
                            attempt=attempt,
                            next_attempt=decision.next_attempt or attempt + 1,
                            delay_ms=decision.delay_ms,
                            reason=decision.reason,
                        )
                    events.append(
                        ConnectorRetryScheduled(
                            occurred_at=event_time(),
                            connector=connector.name,
                            operation=resolved_operation.value,
                            correlation_id=resolved_correlation_id,
                            attempt=attempt,
                            next_attempt=decision.next_attempt or attempt + 1,
                            delay_ms=decision.delay_ms,
                            reason=decision.reason,
                        )
                    )
                    self._record_audit(
                        db,
                        requester_id=requester_id,
                        target_user_id=target_user_id,
                        action=ACTION_CONNECTOR_RETRY_SCHEDULED,
                        result="succeeded",
                        reason=(
                            f"Retry scheduled for {connector.name} "
                            f"{resolved_operation.value}: {decision.reason}"
                        ),
                        correlation_id=resolved_correlation_id,
                    )
                    self._record_audit(
                        db,
                        requester_id=requester_id,
                        target_user_id=target_user_id,
                        action=ACTION_PROVISIONING_RETRY_RECORDED,
                        result="succeeded",
                        reason=(
                            f"Retry recorded for {connector.name} "
                            f"{resolved_operation.value}: {decision.reason}"
                        ),
                        correlation_id=resolved_correlation_id,
                    )
                    attempt += 1
                    continue

                duration_ms = (perf_counter() - started_at) * 1000
                result = self._result_from_exception(
                    connector=connector,
                    operation=resolved_operation,
                    exc=exc,
                    correlation_id=resolved_correlation_id,
                    duration_ms=round(duration_ms, 3),
                )
                events.extend(
                    [
                        ConnectorFailed(
                            occurred_at=event_time(),
                            connector=connector.name,
                            operation=resolved_operation.value,
                            correlation_id=resolved_correlation_id,
                            attempt=attempt,
                            retryable=result.retryable,
                            message=result.message,
                        ),
                        ProvisioningFailed(
                            occurred_at=event_time(),
                            connector=connector.name,
                            operation=resolved_operation.value,
                            correlation_id=resolved_correlation_id,
                            message=result.message,
                        ),
                    ]
                )
                metrics_registry.increment("connector_failures_total")
                log_event(
                    "connector_execution",
                    status="failed",
                    connector=connector.name,
                    operation=resolved_operation.value,
                    attempt=attempt,
                    retryable=result.retryable,
                    message=result.message,
                    correlation_id=resolved_correlation_id,
                )
                self._record_audit(
                    db,
                    requester_id=requester_id,
                    target_user_id=target_user_id,
                    action=ACTION_CONNECTOR_FAILURE,
                    result="denied",
                    reason=result.message,
                    correlation_id=resolved_correlation_id,
                )
                if job_service is not None and job is not None:
                    job_service.fail_job(
                        job,
                        status=result.status.value,
                        message=result.message,
                        attempt=attempt,
                        duration_ms=result.duration_ms,
                        retryable=result.retryable,
                        details=result.details,
                    )
                    self._record_audit(
                        db,
                        requester_id=requester_id,
                        target_user_id=target_user_id,
                        action=ACTION_PROVISIONING_JOB_FAILED,
                        result="denied",
                        reason=(
                            f"Provisioning job {job.id} failed: " f"{result.message}"
                        ),
                        correlation_id=resolved_correlation_id,
                    )
                    job_service.publish_pending_events()
                publish_domain_events(events)
                return result

            if job_service is not None and job is not None:
                job_service.complete_job(
                    job,
                    status=result.status.value,
                    message=result.message,
                    attempt=attempt,
                    duration_ms=result.duration_ms,
                    retryable=result.retryable,
                    details=result.details,
                )
            events.extend(
                [
                    ConnectorSucceeded(
                        occurred_at=event_time(),
                        connector=connector.name,
                        operation=resolved_operation.value,
                        correlation_id=resolved_correlation_id,
                        attempt=attempt,
                        duration_ms=result.duration_ms,
                    ),
                    ProvisioningCompleted(
                        occurred_at=event_time(),
                        connector=connector.name,
                        operation=resolved_operation.value,
                        correlation_id=resolved_correlation_id,
                        status=result.status.value,
                    ),
                ]
            )
            metrics_registry.increment("connector_success_total")
            log_event(
                "connector_execution",
                status=result.status.value,
                connector=connector.name,
                operation=resolved_operation.value,
                attempt=attempt,
                duration_ms=result.duration_ms,
                correlation_id=resolved_correlation_id,
            )
            self._record_audit(
                db,
                requester_id=requester_id,
                target_user_id=target_user_id,
                action=ACTION_CONNECTOR_SUCCESS,
                result="succeeded",
                reason=result.message,
                correlation_id=resolved_correlation_id,
            )
            self._record_audit(
                db,
                requester_id=requester_id,
                target_user_id=target_user_id,
                action=ACTION_PROVISIONING_COMPLETED,
                result="succeeded",
                reason=(
                    f"Provisioning completed for {connector.name} "
                    f"{resolved_operation.value}"
                ),
                correlation_id=resolved_correlation_id,
            )
            if job_service is not None and job is not None:
                self._record_audit(
                    db,
                    requester_id=requester_id,
                    target_user_id=target_user_id,
                    action=ACTION_PROVISIONING_JOB_COMPLETED,
                    result="succeeded",
                    reason=(
                        f"Provisioning job {job.id} completed for "
                        f"{connector.name} {resolved_operation.value}"
                    ),
                    correlation_id=resolved_correlation_id,
                )
                job_service.publish_pending_events()
            publish_domain_events(events)
            return result

    def _call_connector(
        self,
        connector: IdentityConnector,
        operation: ConnectorOperation,
        payload: Mapping[str, Any],
        *,
        correlation_id: str,
    ) -> ConnectorResult:
        if operation == ConnectorOperation.CREATE_USER:
            return connector.create_user(payload, correlation_id=correlation_id)
        if operation == ConnectorOperation.UPDATE_USER:
            return connector.update_user(
                _require_payload_value(payload, "user_id"),
                payload,
                correlation_id=correlation_id,
            )
        if operation == ConnectorOperation.DISABLE_USER:
            return connector.disable_user(
                _require_payload_value(payload, "user_id"),
                correlation_id=correlation_id,
            )
        if operation == ConnectorOperation.DELETE_USER:
            return connector.delete_user(
                _require_payload_value(payload, "user_id"),
                correlation_id=correlation_id,
            )
        if operation == ConnectorOperation.CREATE_GROUP:
            return connector.create_group(payload, correlation_id=correlation_id)
        if operation == ConnectorOperation.UPDATE_GROUP:
            return connector.update_group(
                _require_payload_value(payload, "group_id"),
                payload,
                correlation_id=correlation_id,
            )
        if operation == ConnectorOperation.DELETE_GROUP:
            return connector.delete_group(
                _require_payload_value(payload, "group_id"),
                correlation_id=correlation_id,
            )
        if operation == ConnectorOperation.ADD_GROUP_MEMBER:
            return connector.add_group_member(
                _require_payload_value(payload, "group_id"),
                _require_payload_value(payload, "user_id"),
                correlation_id=correlation_id,
            )
        if operation == ConnectorOperation.REMOVE_GROUP_MEMBER:
            return connector.remove_group_member(
                _require_payload_value(payload, "group_id"),
                _require_payload_value(payload, "user_id"),
                correlation_id=correlation_id,
            )
        if operation == ConnectorOperation.GRANT_ENTITLEMENT:
            return connector.grant_entitlement(
                _require_payload_value(payload, "user_id"),
                _require_mapping(payload, "entitlement"),
                correlation_id=correlation_id,
            )
        if operation == ConnectorOperation.REVOKE_ENTITLEMENT:
            return connector.revoke_entitlement(
                _require_payload_value(payload, "user_id"),
                _require_mapping(payload, "entitlement"),
                correlation_id=correlation_id,
            )

        raise ValidationError(f"Unsupported provisioning operation: {operation}")

    def _result_from_exception(
        self,
        *,
        connector: IdentityConnector,
        operation: ConnectorOperation,
        exc: Exception,
        correlation_id: str,
        duration_ms: float,
    ) -> ConnectorResult:
        retryable = bool(getattr(exc, "retryable", False))
        details = getattr(exc, "details", {})
        details = dict(details) if isinstance(details, dict) else {}
        details["exception_type"] = exc.__class__.__name__

        return ConnectorResult.failed(
            connector=connector.name,
            operation=operation,
            message=str(exc),
            retryable=retryable,
            correlation_id=correlation_id,
            duration_ms=duration_ms,
            details=details,
        )

    def _record_audit(
        self,
        db: Session | None,
        *,
        requester_id: int | None,
        target_user_id: int | None,
        action: str,
        result: str,
        reason: str,
        correlation_id: str,
    ) -> None:
        if db is None or requester_id is None or target_user_id is None:
            return

        entitlement = _get_connector_audit_entitlement(db)
        create_audit_event(
            db,
            requester_id=requester_id,
            target_user_id=target_user_id,
            action=action,
            application_id=entitlement.application_id,
            entitlement_id=entitlement.id,
            result=result,
            reason=reason,
            correlation_id=correlation_id,
        )


def _require_payload_value(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None or str(value).strip() == "":
        raise ValidationError(f"Provisioning payload requires {key}")

    return str(value)


def _require_mapping(
    payload: Mapping[str, Any],
    key: str,
) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValidationError(f"Provisioning payload requires object {key}")

    return value


def _infer_target_type(operation: ConnectorOperation) -> str:
    if operation in {
        ConnectorOperation.CREATE_USER,
        ConnectorOperation.UPDATE_USER,
        ConnectorOperation.DISABLE_USER,
        ConnectorOperation.DELETE_USER,
    }:
        return "user"
    if operation in {
        ConnectorOperation.CREATE_GROUP,
        ConnectorOperation.UPDATE_GROUP,
        ConnectorOperation.DELETE_GROUP,
        ConnectorOperation.ADD_GROUP_MEMBER,
        ConnectorOperation.REMOVE_GROUP_MEMBER,
    }:
        return "group"
    if operation in {
        ConnectorOperation.GRANT_ENTITLEMENT,
        ConnectorOperation.REVOKE_ENTITLEMENT,
    }:
        return "entitlement"

    return "connector"


def _infer_target_id(
    operation: ConnectorOperation,
    payload: Mapping[str, Any],
) -> str | None:
    if operation == ConnectorOperation.CREATE_USER:
        return _optional_payload_value(payload, "email")
    if operation == ConnectorOperation.CREATE_GROUP:
        return _optional_payload_value(payload, "display_name")
    if operation in {
        ConnectorOperation.UPDATE_USER,
        ConnectorOperation.DISABLE_USER,
        ConnectorOperation.DELETE_USER,
        ConnectorOperation.GRANT_ENTITLEMENT,
        ConnectorOperation.REVOKE_ENTITLEMENT,
    }:
        return _optional_payload_value(payload, "user_id")
    if operation in {
        ConnectorOperation.UPDATE_GROUP,
        ConnectorOperation.DELETE_GROUP,
        ConnectorOperation.ADD_GROUP_MEMBER,
        ConnectorOperation.REMOVE_GROUP_MEMBER,
    }:
        return _optional_payload_value(payload, "group_id")

    return None


def _optional_payload_value(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None or str(value).strip() == "":
        return None

    return str(value)


def _get_connector_audit_entitlement(db: Session) -> Entitlement:
    entitlement = db.scalar(
        select(Entitlement)
        .join(Application)
        .where(
            Application.slug == CONNECTOR_AUDIT_APPLICATION_SLUG,
            Entitlement.slug == CONNECTOR_AUDIT_ENTITLEMENT_SLUG,
        )
    )
    if entitlement is None:
        raise RuntimeError("Connector audit entitlement is not seeded")

    return entitlement
