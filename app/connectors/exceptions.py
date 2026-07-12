from __future__ import annotations

from typing import Any


class ConnectorError(Exception):
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        connector: str | None = None,
        operation: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.connector = connector
        self.operation = operation
        self.details = details or {}


class AuthenticationError(ConnectorError):
    pass


class AuthorizationError(ConnectorError):
    pass


class RetryableConnectorError(ConnectorError):
    retryable = True


class RateLimitError(RetryableConnectorError):
    def __init__(
        self,
        message: str,
        *,
        connector: str | None = None,
        operation: str | None = None,
        retry_after_ms: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged_details = dict(details or {})
        if retry_after_ms is not None:
            merged_details["retry_after_ms"] = retry_after_ms

        super().__init__(
            message,
            connector=connector,
            operation=operation,
            details=merged_details,
        )
        self.retry_after_ms = retry_after_ms


class TimeoutError(RetryableConnectorError):
    pass


class ValidationError(ConnectorError):
    pass


class ConfigurationError(ConnectorError):
    pass


class UnknownConnectorError(ConfigurationError):
    def __init__(self, connector: str) -> None:
        super().__init__(f"Unknown connector: {connector}", connector=connector)


class UnsupportedConnectorOperationError(ConnectorError):
    def __init__(self, connector: str, operation: str) -> None:
        super().__init__(
            f"Connector {connector!r} does not support operation {operation!r}",
            connector=connector,
            operation=operation,
        )
