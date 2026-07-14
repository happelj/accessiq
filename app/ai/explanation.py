from __future__ import annotations

from time import perf_counter

from .config import AISettings
from .context import AIContextAssembler
from .models import (
    AIChatRequest,
    AIChatResponse,
    AIExplainRequest,
    AIExplanationResponse,
    AIExplanationTiming,
    ConversationMessage,
)
from .prompt import build_prompt
from .providers import LLMProvider
from .providers.base import (
    ProviderConfigurationError,
    ProviderFailureError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from .conversation import ConversationStore


class AIExplanationError(Exception):
    status_code = 500


class AIProviderNotFoundError(AIExplanationError):
    status_code = 404


class AIProviderUnavailableError(AIExplanationError):
    status_code = 503


class AIProviderTimeoutError(AIExplanationError):
    status_code = 504


class AIProviderRateLimitError(AIExplanationError):
    status_code = 429


class AIProviderFailureError(AIExplanationError):
    status_code = 502


class AIExplanationService:
    def __init__(
        self,
        *,
        assembler: AIContextAssembler,
        providers: dict[str, LLMProvider],
        settings: AISettings,
        conversations: ConversationStore,
    ) -> None:
        self.assembler = assembler
        self.providers = providers
        self.settings = settings
        self.conversations = conversations

    def explain(self, request: AIExplainRequest) -> AIExplanationResponse:
        started = perf_counter()
        context = self.assembler.assemble(request)
        context_ms = _elapsed_ms(started)
        prompt = build_prompt(context)
        provider = self._resolve_provider(request.provider)
        provider_started = perf_counter()

        try:
            result = provider.generate(
                prompt,
                timeout_seconds=self.settings.timeout_seconds,
                max_tokens=min(request.max_tokens, self.settings.max_tokens),
            )
        except (ProviderConfigurationError, ProviderUnavailableError) as exc:
            raise AIProviderUnavailableError(str(exc)) from exc
        except ProviderTimeoutError as exc:
            raise AIProviderTimeoutError(str(exc)) from exc
        except ProviderRateLimitError as exc:
            raise AIProviderRateLimitError(str(exc)) from exc
        except ProviderFailureError as exc:
            raise AIProviderFailureError(str(exc)) from exc

        provider_ms = _elapsed_ms(provider_started)
        return AIExplanationResponse(
            answer=result.answer,
            citations=result.citations or context.citations,
            evidence=context.evidence,
            provider=provider.metadata(),
            timing=AIExplanationTiming(
                context_ms=context_ms,
                provider_ms=provider_ms,
                total_ms=_elapsed_ms(started),
            ),
            intent=context.intent,
            context=context,
        )

    def chat(self, request: AIChatRequest) -> AIChatResponse:
        conversation = self.conversations.get_or_create(
            request.conversation_id,
            metadata={"provider": request.provider or self.settings.provider},
        )
        self.conversations.append_message(
            conversation.conversation_id,
            role="user",
            content=request.question,
            metadata={"intent_request": True},
        )
        explanation = self.explain(request)
        assistant_message = self.conversations.append_message(
            conversation.conversation_id,
            role="assistant",
            content=explanation.answer,
            metadata={
                "provider": explanation.provider.name,
                "citation_count": len(explanation.citations),
            },
        )
        return AIChatResponse(
            conversation_id=conversation.conversation_id,
            message=assistant_message,
            explanation=explanation,
            conversation=conversation,
        )

    def _resolve_provider(self, provider_name: str | None) -> LLMProvider:
        if not self.settings.enabled:
            raise AIProviderUnavailableError("AI is disabled by AI_ENABLED")

        resolved_name = (provider_name or self.settings.provider).strip().lower()
        provider = self.providers.get(resolved_name)
        if provider is None:
            raise AIProviderNotFoundError(f"Unknown LLM provider: {resolved_name}")
        if not provider.metadata().available:
            raise AIProviderUnavailableError(provider.health().message)

        return provider


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)
