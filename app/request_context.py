from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import Request

CORRELATION_ID_HEADER = "X-Correlation-ID"


@dataclass
class AuthenticatedUserContext:
    id: int
    email: str
    operator_role: str


@dataclass
class RequestContext:
    correlation_id: str
    request_start: datetime
    client_ip: str | None
    user_agent: str | None
    authenticated_user: AuthenticatedUserContext | None = None


_current_request_context: ContextVar[RequestContext | None] = ContextVar(
    "current_request_context",
    default=None,
)


def create_request_context(request: Request) -> RequestContext:
    correlation_id = request.headers.get(CORRELATION_ID_HEADER)
    if correlation_id is None or correlation_id.strip() == "":
        correlation_id = str(uuid4())

    return RequestContext(
        correlation_id=correlation_id,
        request_start=datetime.now(UTC),
        client_ip=request.client.host if request.client is not None else None,
        user_agent=request.headers.get("user-agent"),
    )


def set_request_context(context: RequestContext) -> Token[RequestContext | None]:
    return _current_request_context.set(context)


def reset_request_context(token: Token[RequestContext | None]) -> None:
    _current_request_context.reset(token)


def get_request_context() -> RequestContext | None:
    return _current_request_context.get()


def set_authenticated_user(user: Any) -> None:
    context = get_request_context()
    if context is None:
        return

    context.authenticated_user = AuthenticatedUserContext(
        id=user.id,
        email=user.email,
        operator_role=user.operator_role,
    )
