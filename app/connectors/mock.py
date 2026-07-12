from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from time import perf_counter
from typing import Any

from .base import IdentityConnector
from .exceptions import (
    ConnectorError,
    RateLimitError,
    RetryableConnectorError,
    TimeoutError,
    UnsupportedConnectorOperationError,
    ValidationError,
)
from .results import (
    ConnectorHealth,
    ConnectorHealthStatus,
    ConnectorOperation,
    ConnectorResult,
)

MUTATING_CONNECTOR_OPERATIONS = tuple(
    operation
    for operation in ConnectorOperation
    if operation is not ConnectorOperation.HEALTH_CHECK
)


class ConnectorSimulationMode(StrEnum):
    SUCCESS = "success"
    VALIDATION_FAILURE = "validation_failure"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    RETRYABLE_FAILURE = "retryable_failure"
    NON_RETRYABLE_FAILURE = "non_retryable_failure"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class MockConnectorMetadata:
    name: str
    display_name: str


class MockIdentityConnector(IdentityConnector):
    def __init__(
        self,
        *,
        name: str,
        display_name: str,
        enabled: bool = True,
        simulation_mode: ConnectorSimulationMode = ConnectorSimulationMode.SUCCESS,
        failures_before_success: int = 0,
        supported_operations: tuple[ConnectorOperation, ...] = (
            MUTATING_CONNECTOR_OPERATIONS
        ),
    ) -> None:
        if failures_before_success < 0:
            raise ValueError("failures_before_success cannot be negative")

        self._metadata = MockConnectorMetadata(
            name=name,
            display_name=display_name,
        )
        self._enabled = enabled
        self._simulation_mode = simulation_mode
        self._failures_before_success = failures_before_success
        self._supported_operations = supported_operations
        self._attempts: dict[str, int] = {}

    @property
    def name(self) -> str:
        return self._metadata.name

    @property
    def display_name(self) -> str:
        return self._metadata.display_name

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def simulation_mode(self) -> ConnectorSimulationMode:
        return self._simulation_mode

    @property
    def supported_operations(self) -> tuple[ConnectorOperation, ...]:
        return self._supported_operations

    def health_check(self) -> ConnectorHealth:
        if not self.enabled:
            return ConnectorHealth(
                connector=self.name,
                status=ConnectorHealthStatus.UNAVAILABLE,
                message=f"{self.display_name} connector is disabled",
                details={"enabled": False},
            )

        if self.simulation_mode == ConnectorSimulationMode.DEGRADED:
            return ConnectorHealth(
                connector=self.name,
                status=ConnectorHealthStatus.DEGRADED,
                message=f"{self.display_name} connector is degraded",
                details={"simulation_mode": self.simulation_mode.value},
            )

        if self.simulation_mode in {
            ConnectorSimulationMode.UNAVAILABLE,
            ConnectorSimulationMode.TIMEOUT,
        }:
            return ConnectorHealth(
                connector=self.name,
                status=ConnectorHealthStatus.UNAVAILABLE,
                message=f"{self.display_name} connector is unavailable",
                details={"simulation_mode": self.simulation_mode.value},
            )

        return ConnectorHealth(
            connector=self.name,
            status=ConnectorHealthStatus.HEALTHY,
            message=f"{self.display_name} connector is healthy",
            details={"simulation_mode": self.simulation_mode.value},
        )

    def create_user(
        self,
        user: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        return self._execute(
            ConnectorOperation.CREATE_USER,
            user,
            correlation_id=correlation_id,
        )

    def update_user(
        self,
        user_id: str,
        user: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        payload = {"user_id": user_id, "user": dict(user)}
        return self._execute(
            ConnectorOperation.UPDATE_USER,
            payload,
            correlation_id=correlation_id,
        )

    def disable_user(
        self,
        user_id: str,
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        return self._execute(
            ConnectorOperation.DISABLE_USER,
            {"user_id": user_id},
            correlation_id=correlation_id,
        )

    def delete_user(
        self,
        user_id: str,
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        return self._execute(
            ConnectorOperation.DELETE_USER,
            {"user_id": user_id},
            correlation_id=correlation_id,
        )

    def create_group(
        self,
        group: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        return self._execute(
            ConnectorOperation.CREATE_GROUP,
            group,
            correlation_id=correlation_id,
        )

    def update_group(
        self,
        group_id: str,
        group: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        payload = {"group_id": group_id, "group": dict(group)}
        return self._execute(
            ConnectorOperation.UPDATE_GROUP,
            payload,
            correlation_id=correlation_id,
        )

    def delete_group(
        self,
        group_id: str,
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        return self._execute(
            ConnectorOperation.DELETE_GROUP,
            {"group_id": group_id},
            correlation_id=correlation_id,
        )

    def add_group_member(
        self,
        group_id: str,
        user_id: str,
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        return self._execute(
            ConnectorOperation.ADD_GROUP_MEMBER,
            {"group_id": group_id, "user_id": user_id},
            correlation_id=correlation_id,
        )

    def remove_group_member(
        self,
        group_id: str,
        user_id: str,
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        return self._execute(
            ConnectorOperation.REMOVE_GROUP_MEMBER,
            {"group_id": group_id, "user_id": user_id},
            correlation_id=correlation_id,
        )

    def grant_entitlement(
        self,
        user_id: str,
        entitlement: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        payload = {"user_id": user_id, "entitlement": dict(entitlement)}
        return self._execute(
            ConnectorOperation.GRANT_ENTITLEMENT,
            payload,
            correlation_id=correlation_id,
        )

    def revoke_entitlement(
        self,
        user_id: str,
        entitlement: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        payload = {"user_id": user_id, "entitlement": dict(entitlement)}
        return self._execute(
            ConnectorOperation.REVOKE_ENTITLEMENT,
            payload,
            correlation_id=correlation_id,
        )

    def _execute(
        self,
        operation: ConnectorOperation,
        payload: Mapping[str, Any],
        *,
        correlation_id: str | None,
    ) -> ConnectorResult:
        if operation not in self.supported_operations:
            raise UnsupportedConnectorOperationError(self.name, operation.value)

        if not self.enabled:
            return ConnectorResult.skipped(
                connector=self.name,
                operation=operation,
                message=f"{self.display_name} connector is disabled",
                correlation_id=correlation_id,
                details={"enabled": False},
            )

        started_at = perf_counter()
        attempt = self._record_attempt(operation, correlation_id)

        if attempt <= self._failures_before_success:
            raise RetryableConnectorError(
                "Simulated retryable failure before success",
                connector=self.name,
                operation=operation.value,
                details={"attempt": attempt},
            )

        self._raise_for_simulation(operation)
        duration_ms = (perf_counter() - started_at) * 1000

        return ConnectorResult.success(
            connector=self.name,
            operation=operation,
            message=(
                f"{self.display_name} {operation.value} simulated successfully"
            ),
            duration_ms=round(duration_ms, 3),
            correlation_id=correlation_id,
            details={
                "payload": dict(payload),
                "attempt": attempt,
                "simulation_mode": self.simulation_mode.value,
            },
        )

    def _record_attempt(
        self,
        operation: ConnectorOperation,
        correlation_id: str | None,
    ) -> int:
        key = f"{operation.value}:{correlation_id or 'default'}"
        attempt = self._attempts.get(key, 0) + 1
        self._attempts[key] = attempt
        return attempt

    def _raise_for_simulation(self, operation: ConnectorOperation) -> None:
        common = {
            "connector": self.name,
            "operation": operation.value,
        }

        if self.simulation_mode == ConnectorSimulationMode.VALIDATION_FAILURE:
            raise ValidationError("Simulated validation failure", **common)

        if self.simulation_mode == ConnectorSimulationMode.TIMEOUT:
            raise TimeoutError("Simulated connector timeout", **common)

        if self.simulation_mode == ConnectorSimulationMode.RATE_LIMIT:
            raise RateLimitError(
                "Simulated connector rate limit",
                retry_after_ms=1_000,
                **common,
            )

        if self.simulation_mode == ConnectorSimulationMode.RETRYABLE_FAILURE:
            raise RetryableConnectorError("Simulated retryable failure", **common)

        if self.simulation_mode == ConnectorSimulationMode.NON_RETRYABLE_FAILURE:
            raise ConnectorError("Simulated non-retryable failure", **common)

        if self.simulation_mode == ConnectorSimulationMode.UNAVAILABLE:
            raise RetryableConnectorError("Simulated connector unavailable", **common)
