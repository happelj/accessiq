from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class AISettings:
    enabled: bool
    provider: str
    openai_api_key: str | None
    anthropic_api_key: str | None
    timeout_seconds: int
    max_tokens: int
    openai_model: str
    anthropic_model: str


@lru_cache
def get_ai_settings() -> AISettings:
    return AISettings(
        enabled=_get_bool_env("AI_ENABLED", True),
        provider=os.getenv("LLM_PROVIDER", "mock").strip().lower() or "mock",
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        timeout_seconds=_get_int_env("AI_TIMEOUT", 30),
        max_tokens=_get_int_env("AI_MAX_TOKENS", 1200),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
    )
