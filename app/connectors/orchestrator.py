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
from .base import IdentityConnector
from .exceptions import ConnectorError, ValidationError
from .registry import ConnectorRegistry
from .results import ConnectorOperation, ConnectorResult, ConnectorStatus
from .retry import RetryPolicy

CONNECTOR_AUDIT_APPLICATION_SLUG = "connector-framework"
CONNECTOR_AUDIT_ENTITLEMENT_SLUG = "connector-execution"

ACTION_CONNECTOR_INVOCATION = "connector_invocation"
ACTION_CONNECTOR_SUCCESS = "connector_success"
ACTION_CONNECTOR_FAILURE = "connector_failure"
ACTION_CONNECTOR_RETRY_SCHEDULED = "connector_retry_scheduled"
ACTION_PROVISIONING_COMPLETED = "connector_provisioning_completed"


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
        resolved_correlation_id = correlation_id or str(uuid4())
        connector = self.registry.get(connector_name)
        operation_payload = dict(payload or {})
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
            events.append(
                ConnectorCalled(
                    occurred_at=event_time(),
                    connector=connector.name,
                    operation=resolved_operation.value,
                    correlation_id=resolved_correlation_id,
                    attempt=attempt,
                )
            )
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
                self._record_audit(
                    db,
                    requester_id=requester_id,
                    target_user_id=target_user_id,
                    action=ACTION_CONNECTOR_FAILURE,
                    result="denied",
                    reason=result.message,
                )
                publish_domain_events(events)
                return result

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
            self._record_audit(
                db,
                requester_id=requester_id,
                target_user_id=target_user_id,
                action=ACTION_CONNECTOR_SUCCESS,
                result="succeeded",
                reason=result.message,
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
            )
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
