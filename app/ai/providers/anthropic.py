from __future__ import annotations

from urllib import error, request
import json
import socket

from ..config import AISettings
from ..models import (
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


class AnthropicProvider(LLMProvider):
    def __init__(self, settings: AISettings) -> None:
        self.settings = settings

    def provider_name(self) -> str:
        return "anthropic"

    def metadata(self) -> LLMProviderMetadata:
        available = bool(self.settings.anthropic_api_key)
        return LLMProviderMetadata(
            name=self.provider_name(),
            display_name="Anthropic",
            enabled=self.settings.enabled,
            available=self.settings.enabled and available,
            supports_streaming=True,
            model=self.settings.anthropic_model,
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
        if not self.settings.anthropic_api_key:
            return LLMProviderHealth(
                provider=self.provider_name(),
                status="configuration_missing",
                message="ANTHROPIC_API_KEY is not configured.",
                metadata=metadata,
            )
        return LLMProviderHealth(
            provider=self.provider_name(),
            status="healthy",
            message="Anthropic provider is configured.",
            metadata=metadata,
        )

    def generate(
        self,
        prompt: StructuredPrompt,
        *,
        timeout_seconds: int,
        max_tokens: int,
    ) -> LLMGenerationResult:
        if not self.settings.anthropic_api_key:
            raise ProviderConfigurationError("ANTHROPIC_API_KEY is not configured")

        system_content = "\n".join(prompt.system_instructions + prompt.constraints)
        user_content = next(
            message.content for message in prompt.messages if message.role == "user"
        )
        payload = json.dumps(
            {
                "model": self.settings.anthropic_model,
                "max_tokens": max_tokens,
                "system": system_content,
                "messages": [{"role": "user", "content": user_content}],
            }
        ).encode("utf-8")
        api_request = request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "x-api-key": self.settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(api_request, timeout=timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except socket.timeout as exc:
            raise ProviderTimeoutError("Anthropic provider timed out") from exc
        except error.HTTPError as exc:
            if exc.code == 429:
                raise ProviderRateLimitError(
                    "Anthropic provider rate limited the request"
                ) from exc
            raise ProviderFailureError(
                f"Anthropic provider failed with HTTP {exc.code}"
            ) from exc
        except OSError as exc:
            raise ProviderFailureError("Anthropic provider request failed") from exc

        answer = " ".join(
            item.get("text", "")
            for item in body.get("content", [])
            if item.get("type") == "text"
        ).strip()
        if not answer:
            raise ProviderFailureError("Anthropic provider returned an empty answer")

        return LLMGenerationResult(
            answer=answer,
            provider=self.provider_name(),
            model=self.settings.anthropic_model,
            citations=prompt.citations,
            metadata={"raw_provider": "anthropic"},
        )
