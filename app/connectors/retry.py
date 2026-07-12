from __future__ import annotations

from dataclasses import dataclass

from .exceptions import RetryableConnectorError


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    attempt: int
    next_attempt: int | None
    delay_ms: int
    reason: str


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_ms: int = 100
    max_delay_ms: int = 1_000
    retryable_exception_types: tuple[type[Exception], ...] = (
        RetryableConnectorError,
    )

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_ms < 0:
            raise ValueError("base_delay_ms cannot be negative")
        if self.max_delay_ms < self.base_delay_ms:
            raise ValueError("max_delay_ms must be greater than base_delay_ms")

    def is_retryable_exception(self, exc: Exception) -> bool:
        if isinstance(exc, self.retryable_exception_types):
            return True

        return bool(getattr(exc, "retryable", False))

    def should_retry(self, exc: Exception, *, attempt: int) -> bool:
        return self.is_retryable_exception(exc) and attempt < self.max_attempts

    def next_delay_ms(self, *, attempt: int) -> int:
        if attempt < 1:
            raise ValueError("attempt must be at least 1")

        delay = self.base_delay_ms * (2 ** (attempt - 1))
        return min(delay, self.max_delay_ms)

    def decision(self, exc: Exception, *, attempt: int) -> RetryDecision:
        should_retry = self.should_retry(exc, attempt=attempt)
        return RetryDecision(
            should_retry=should_retry,
            attempt=attempt,
            next_attempt=attempt + 1 if should_retry else None,
            delay_ms=self.next_delay_ms(attempt=attempt) if should_retry else 0,
            reason=str(exc),
        )
