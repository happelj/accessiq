from __future__ import annotations

from ..config import AISettings, get_ai_settings
from .anthropic import AnthropicProvider
from .base import (
    LLMProvider,
    LLMProviderError,
    ProviderConfigurationError,
    ProviderFailureError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from .mock import MockLLMProvider
from .openai import OpenAIProvider


def build_provider_registry(
    settings: AISettings | None = None,
) -> dict[str, LLMProvider]:
    resolved_settings = settings or get_ai_settings()
    providers: list[LLMProvider] = [
        MockLLMProvider(),
        OpenAIProvider(resolved_settings),
        AnthropicProvider(resolved_settings),
    ]
    return {provider.provider_name(): provider for provider in providers}


__all__ = [
    "AnthropicProvider",
    "LLMProvider",
    "LLMProviderError",
    "MockLLMProvider",
    "OpenAIProvider",
    "ProviderConfigurationError",
    "ProviderFailureError",
    "ProviderRateLimitError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "build_provider_registry",
]
