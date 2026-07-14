from __future__ import annotations

from urllib import error, request
import json
import socket

from ..config import AISettings
from ..models import (
    Citation,
    LLMGenerationResult,
    LLMProviderHealth,
    LLMProviderMetadata,
    StructuredPrompt,
)
from .base import (
    LLMProvider,
    ProviderConfigurationError,
    ProviderFailureError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)


class OpenAIProvider(LLMProvider):
    def __init__(self, settings: AISettings) -> None:
        self.settings = settings

    def provider_name(self) -> str:
        return "openai"

    def metadata(self) -> LLMProviderMetadata:
        available = bool(self.settings.openai_api_key)
        return LLMProviderMetadata(
            name=self.provider_name(),
            display_name="OpenAI",
            enabled=self.settings.enabled,
            available=self.settings.enabled and available,
            supports_streaming=True,
            model=self.settings.openai_model,
            details={"api_key_configured": available},
        )

    def health(self) -> LLMProviderHealth:
        metadata = self.metadata()
        if not self.settings.enabled:
            return LLMProviderHealth(
                provider=self.provider_name(),
                status="disabled",
                message="AI is disabled by AI_ENABLED.",
                metadata=metadata,
            )
        if not self.settings.openai_api_key:
            return LLMProviderHealth(
                provider=self.provider_name(),
                status="configuration_missing",
                message="OPENAI_API_KEY is not configured.",
                metadata=metadata,
            )
        return LLMProviderHealth(
            provider=self.provider_name(),
            status="healthy",
            message="OpenAI provider is configured.",
            metadata=metadata,
        )

    def generate(
        self,
        prompt: StructuredPrompt,
        *,
        timeout_seconds: int,
        max_tokens: int,
    ) -> LLMGenerationResult:
        if not self.settings.openai_api_key:
            raise ProviderConfigurationError("OPENAI_API_KEY is not configured")

        payload = json.dumps(
            {
                "model": self.settings.openai_model,
                "messages": [
                    message.model_dump(mode="json")
                    for message in prompt.messages
                ],
                "max_tokens": max_tokens,
            }
        ).encode("utf-8")
        api_request = request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(api_request, timeout=timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except socket.timeout as exc:
            raise ProviderTimeoutError("OpenAI provider timed out") from exc
        except error.HTTPError as exc:
            if exc.code == 429:
                raise ProviderRateLimitError("OpenAI provider rate limited the request") from exc
            raise ProviderFailureError(f"OpenAI provider failed with HTTP {exc.code}") from exc
        except OSError as exc:
            raise ProviderFailureError("OpenAI provider request failed") from exc

        answer = (
            body.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if not answer:
            raise ProviderFailureError("OpenAI provider returned an empty answer")

        return LLMGenerationResult(
            answer=answer,
            provider=self.provider_name(),
            model=self.settings.openai_model,
            citations=prompt.citations,
            metadata={"raw_provider": "openai"},
        )
