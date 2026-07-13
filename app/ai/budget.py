from __future__ import annotations

from math import ceil

from .models import AIEvidence, TokenBudget


def estimate_tokens(value: str) -> int:
    stripped = value.strip()
    if not stripped:
        return 0
    return max(1, ceil(len(stripped) / 4))


def estimate_evidence_tokens(evidence: AIEvidence) -> int:
    return estimate_tokens(
        " ".join(
            part
            for part in (
                evidence.title,
                evidence.description,
                evidence.reference,
                evidence.correlation_id or "",
            )
            if part
        )
    )


def apply_token_budget(
    evidence: list[AIEvidence],
    *,
    max_tokens: int,
    reserved_tokens: int,
) -> tuple[list[AIEvidence], TokenBudget]:
    available = max(0, max_tokens - reserved_tokens)
    included: list[AIEvidence] = []
    evidence_tokens = 0

    for item in evidence:
        item_tokens = estimate_evidence_tokens(item)
        if evidence_tokens + item_tokens > available:
            continue

        included.append(item.model_copy(update={"token_estimate": item_tokens}))
        evidence_tokens += item_tokens

    omitted_count = len(evidence) - len(included)
    return included, TokenBudget(
        max_tokens=max_tokens,
        reserved_tokens=reserved_tokens,
        evidence_tokens=evidence_tokens,
        total_estimated_tokens=reserved_tokens + evidence_tokens,
        included_evidence_count=len(included),
        omitted_evidence_count=omitted_count,
        truncated=omitted_count > 0,
    )
