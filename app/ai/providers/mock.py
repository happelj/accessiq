from __future__ import annotations

from ..models import (
    Citation,
    LLMGenerationResult,
    LLMProviderHealth,
    LLMProviderMetadata,
    StructuredPrompt,
)
from .base import LLMProvider


class MockLLMProvider(LLMProvider):
    def provider_name(self) -> str:
        return "mock"

    def metadata(self) -> LLMProviderMetadata:
        return LLMProviderMetadata(
            name=self.provider_name(),
            display_name="Deterministic Mock Provider",
            enabled=True,
            available=True,
            supports_streaming=False,
            model="mock-grounded-explainer",
            details={"network": "disabled", "deterministic": True},
        )

    def health(self) -> LLMProviderHealth:
        return LLMProviderHealth(
            provider=self.provider_name(),
            status="healthy",
            message="Mock provider is available and deterministic.",
            metadata=self.metadata(),
        )

    def generate(
        self,
        prompt: StructuredPrompt,
        *,
        timeout_seconds: int,
        max_tokens: int,
    ) -> LLMGenerationResult:
        del timeout_seconds, max_tokens
        evidence = prompt.assembled_evidence
        citations = [
            Citation(
                id=item.id,
                title=item.title,
                reference=item.reference,
                correlation_id=item.correlation_id,
            )
            for item in evidence
        ]

        if not evidence:
            answer = (
                "I do not have enough AccessIQ evidence to explain this. "
                "No authorization decision was made."
            )
        else:
            top_items = evidence[:5]
            facts = " ".join(
                f"{index}. {item.title}: {item.description} "
                f"(reference: {item.reference})."
                for index, item in enumerate(top_items, start=1)
            )
            answer = (
                "Based only on deterministic AccessIQ evidence, here is the "
                f"grounded explanation for: {prompt.user_question} "
                f"{facts} This explanation is informational only; AccessIQ's "
                "policy, provisioning, review, and remediation services remain "
                "authoritative."
            )

        return LLMGenerationResult(
            answer=answer,
            provider=self.provider_name(),
            model=self.metadata().model,
            citations=citations,
            metadata={
                "evidence_count": len(evidence),
                "deterministic": True,
            },
        )
