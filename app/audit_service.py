from sqlalchemy.orm import Session

from .models import AuditEvent
from .observability import log_event, metrics_registry
from .request_context import get_request_context


def create_audit_event(
    db: Session,
    *,
    requester_id: int,
    target_user_id: int,
    action: str,
    application_id: int,
    entitlement_id: int,
    result: str,
    reason: str,
    correlation_id: str | None = None,
) -> AuditEvent:
    context = get_request_context()
    resolved_correlation_id = correlation_id
    if resolved_correlation_id is None and context is not None:
        resolved_correlation_id = context.correlation_id

    event = AuditEvent(
        requester_id=requester_id,
        target_user_id=target_user_id,
        action=action,
        application_id=application_id,
        entitlement_id=entitlement_id,
        result=result,
        reason=reason,
        correlation_id=resolved_correlation_id,
    )

    db.add(event)
    db.flush()
    metrics_registry.increment("audit_events_total")
    log_event(
        "audit_event_recorded",
        status=result,
        audit_action=action,
        requester_id=requester_id,
        target_user_id=target_user_id,
        application_id=application_id,
        entitlement_id=entitlement_id,
        correlation_id=resolved_correlation_id,
    )

    return event
