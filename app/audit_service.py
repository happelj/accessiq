from sqlalchemy.orm import Session

from .models import AuditEvent


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
    event = AuditEvent(
        requester_id=requester_id,
        target_user_id=target_user_id,
        action=action,
        application_id=application_id,
        entitlement_id=entitlement_id,
        result=result,
        reason=reason,
        correlation_id=correlation_id,
    )

    db.add(event)
    db.flush()

    return event
