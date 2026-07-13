from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from .config import get_logging_settings
from .request_context import get_request_context


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._lock = Lock()

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(sorted(self._counters.items()))


metrics_registry = MetricsRegistry()


def configure_logging() -> None:
    settings = get_logging_settings()
    logging.basicConfig(level=settings.log_level)


def log_event(
    event: str,
    *,
    status: str,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    settings = get_logging_settings()
    logger = logging.getLogger(settings.logger_name)
    context = get_request_context()
    payload: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        "status": status,
        **fields,
    }

    if context is not None:
        payload.setdefault("correlation_id", context.correlation_id)
        payload.setdefault("request_start", context.request_start.isoformat())
        payload.setdefault("client_ip", context.client_ip)
        payload.setdefault("user_agent", context.user_agent)
        if context.authenticated_user is not None:
            payload.setdefault(
                "authenticated_user_id",
                context.authenticated_user.id,
            )
            payload.setdefault(
                "authenticated_user_role",
                context.authenticated_user.operator_role,
            )

    logger.log(level, json.dumps(payload, default=str, sort_keys=True))
