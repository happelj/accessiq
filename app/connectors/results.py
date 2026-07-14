from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ConnectorOperation(StrEnum):
    HEALTH_CHECK = "health_check"
    CREATE_USER = "create_user"
    UPDATE_USER = "update_user"
    DISABLE_USER = "disable_user"
    DELETE_USER = "delete_user"
    CREATE_GROUP = "create_group"
    UPDATE_GROUP = "update_group"
    DELETE_GROUP = "delete_group"
    ADD_GROUP_MEMBER = "add_group_member"
    REMOVE_GROUP_MEMBER = "remove_group_member"
    GRANT_ENTITLEMENT = "grant_entitlement"
    REVOKE_ENTITLEMENT = "revoke_entitlement"


class ConnectorStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYABLE = "RETRYABLE"
    SKIPPED = "SKIPPED"


class ConnectorHealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _enum_value(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value

    return value


@dataclass(frozen=True)
class ConnectorResult:
    connector: str
    operation: ConnectorOperation
    status: ConnectorStatus
    message: str
    timestamp: datetime = field(default_factory=_utc_now)
    duration_ms: float = 0.0
    retryable: bool = False
    correlation_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(
        cls,
        *,
        connector: str,
        operation: ConnectorOperation,
        message: str,
        duration_ms: float,
        correlation_id: str | None,
        details: dict[str, Any] | None = None,
    ) -> ConnectorResult:
        return cls(
            connector=connector,
            operation=operation,
            status=ConnectorStatus.SUCCESS,
            message=message,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            details=details or {},
        )

    @classmethod
    def skipped(
        cls,
        *,
        connector: str,
        operation: ConnectorOperation,
        message: str,
        correlation_id: str | None,
        details: dict[str, Any] | None = None,
    ) -> ConnectorResult:
        return cls(
            connector=connector,
            operation=operation,
            status=ConnectorStatus.SKIPPED,
            message=message,
            retryable=False,
            correlation_id=correlation_id,
            details=details or {},
        )

    @classmethod
    def failed(
        cls,
        *,
        connector: str,
        operation: ConnectorOperation,
        message: str,
        retryable: bool,
        correlation_id: str | None,
        duration_ms: float = 0.0,
        details: dict[str, Any] | None = None,
    ) -> ConnectorResult:
        return cls(
            connector=connector,
            operation=operation,
            status=(ConnectorStatus.RETRYABLE if retryable else ConnectorStatus.FAILED),
            message=message,
            duration_ms=duration_ms,
            retryable=retryable,
            correlation_id=correlation_id,
            details=details or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector": self.connector,
            "operation": _enum_value(self.operation),
            "status": _enum_value(self.status),
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "retryable": self.retryable,
            "correlation_id": self.correlation_id,
            "details": self.details,
        }


@dataclass(frozen=True)
class ConnectorHealth:
    connector: str
    status: ConnectorHealthStatus
    message: str
    timestamp: datetime = field(default_factory=_utc_now)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector": self.connector,
            "status": self.status.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }
