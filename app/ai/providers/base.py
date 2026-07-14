from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import (
    LLMGenerationResult,
    LLMProviderHealth,
    LLMProviderMetadata,
    StructuredPrompt,
)


class LLMProviderError(Exception):
    """Base provider exception."""


class ProviderUnavailableError(LLMProviderError):
    """Provider is disabled, missing configuration, or not reachable."""


class ProviderTimeoutError(LLMProviderError):
    """Provider request exceeded the configured timeout."""


class ProviderConfigurationError(ProviderUnavailableError):
    """Provider is missing required configuration."""


class ProviderRateLimitError(LLMProviderError):
    """Provider reported a rate-limit response."""


class ProviderFailureError(LLMProviderError):
    """Provider failed for a non-timeout, non-rate-limit reason."""


class LLMProvider(ABC):
    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def metadata(self) -> LLMProviderMetadata:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> LLMProviderHealth:
        raise NotImplementedError

    @abstractmethod
    def generate(
        self,
        prompt: StructuredPrompt,
        *,
        timeout_seconds: int,
        max_tokens: int,
    ) -> LLMGenerationResult:
        raise NotImplementedError
