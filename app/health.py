from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .config import get_auth_settings, get_connector_settings, get_database_settings
from .connectors.registry import ConnectorRegistry
from .domain.publisher import get_published_events
from .models import AuditEvent, ProvisioningHistory, ProvisioningJob
from .observability import metrics_registry, record_database_query
from .request_context import get_request_context
from .schemas import HealthResponse, SubsystemHealth


def build_health_report(
    *,
    db: Session,
    registry: ConnectorRegistry,
) -> HealthResponse:
    subsystems: dict[str, SubsystemHealth] = {
        "database": _database_health(db),
        "connectors": _connector_health(registry),
        "audit": _audit_health(db),
        "provisioning": _provisioning_health(db),
        "domain_events": _domain_event_health(),
        "configuration": _configuration_health(registry),
    }
    overall_status = (
        "healthy"
        if all(subsystem.status == "healthy" for subsystem in subsystems.values())
        else "degraded"
    )
    context = get_request_context()

    return HealthResponse(
        status=overall_status,
        correlation_id=context.correlation_id if context is not None else None,
        subsystems=subsystems,
        metrics=metrics_registry.snapshot(),
    )


def _database_health(db: Session) -> SubsystemHealth:
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        record_database_query(operation="health_check", status="failed")
        raise

    record_database_query(operation="health_check", status="succeeded")
    settings = get_database_settings()
    return SubsystemHealth(
        status="healthy",
        details={"backend": settings.database_backend},
    )


def _connector_health(registry: ConnectorRegistry) -> SubsystemHealth:
    connectors = registry.list()
    connector_statuses = {
        connector.name: connector.health_check().status for connector in connectors
    }
    subsystem_status = (
        "healthy"
        if all(str(status) == "HEALTHY" for status in connector_statuses.values())
        else "degraded"
    )
    return SubsystemHealth(
        status=subsystem_status,
        details={
            "enabled_count": len(connectors),
            "connectors": connector_statuses,
        },
    )


def _audit_health(db: Session) -> SubsystemHealth:
    event_count = _count_rows(db, AuditEvent)
    return SubsystemHealth(
        status="healthy",
        details={"event_count": event_count},
    )


def _provisioning_health(db: Session) -> SubsystemHealth:
    job_count = _count_rows(db, ProvisioningJob)
    history_count = _count_rows(db, ProvisioningHistory)
    return SubsystemHealth(
        status="healthy",
        details={
            "job_count": job_count,
            "history_count": history_count,
        },
    )


def _domain_event_health() -> SubsystemHealth:
    return SubsystemHealth(
        status="healthy",
        details={"published_event_count": len(get_published_events())},
    )


def _configuration_health(registry: ConnectorRegistry) -> SubsystemHealth:
    auth_settings = get_auth_settings()
    connector_settings = get_connector_settings()
    database_settings = get_database_settings()
    enabled_connectors = [connector.name for connector in registry.list()]

    return SubsystemHealth(
        status="healthy",
        details={
            "jwt_algorithm": auth_settings.jwt_algorithm,
            "token_expiration_minutes": auth_settings.access_token_expire_minutes,
            "database_backend": database_settings.database_backend,
            "enabled_connectors": enabled_connectors,
            "connector_flags": {
                "salesforce": connector_settings.enable_salesforce_connector,
                "github": connector_settings.enable_github_connector,
                "zendesk": connector_settings.enable_zendesk_connector,
                "finance": connector_settings.enable_finance_connector,
            },
        },
    )


def _count_rows(db: Session, model: type[object]) -> int:
    value = db.scalar(select(func.count()).select_from(model))
    return int(value or 0)
