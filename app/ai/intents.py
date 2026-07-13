from __future__ import annotations

import re

from .models import AIContextRequest, IntentClassification, IntentType


_WHITESPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^a-z0-9\s#_-]")


def classify_intent(request: AIContextRequest) -> IntentClassification:
    normalized = normalize_question(request.question)
    matched_rules: list[str] = []

    intent = IntentType.GENERAL
    confidence = 0.55

    if _contains_any(
        normalized,
        "cant access",
        "can't access",
        "cannot access",
        "can not access",
        "why cant",
        "why can't",
        "access denied",
        "does not have access",
        "doesnt have access",
    ):
        intent = IntentType.ACCESS_GAP
        confidence = 0.95
        matched_rules.append("access_gap_phrase")
    elif _contains_any(normalized, "access path", "show path", "shortest path"):
        intent = IntentType.ACCESS_PATH
        confidence = 0.95
        matched_rules.append("access_path_phrase")
    elif _contains_any(normalized, "manager chain", "management chain"):
        intent = IntentType.MANAGER_CHAIN
        confidence = 0.95
        matched_rules.append("manager_chain_phrase")
    elif "provision" in normalized:
        intent = IntentType.PROVISIONING
        confidence = 0.9
        matched_rules.append("provisioning_keyword")
    elif "remediat" in normalized:
        intent = IntentType.REMEDIATION
        confidence = 0.9
        matched_rules.append("remediation_keyword")
    elif _contains_any(normalized, "review", "certification", "certify"):
        intent = IntentType.REVIEW
        confidence = 0.9
        matched_rules.append("review_keyword")
    elif _contains_any(
        normalized,
        "why does",
        "why do",
        "why has",
        "why have",
        "has access",
        "have access",
        "explain access",
    ):
        intent = IntentType.EXPLAIN_ACCESS
        confidence = 0.85
        matched_rules.append("explain_access_phrase")

    if not matched_rules:
        matched_rules.append("fallback_general")

    return IntentClassification(
        intent=intent,
        confidence=confidence,
        matched_rules=matched_rules,
        normalized_question=normalized,
        user_id=request.user_id or _extract_id(normalized, "user"),
        application_id=(
            request.application_id
            or _extract_id(normalized, "application")
            or _extract_id(normalized, "app")
        ),
        entitlement_id=request.entitlement_id or _extract_id(normalized, "entitlement"),
    )


def normalize_question(question: str) -> str:
    lowered = question.strip().lower()
    without_punctuation = _PUNCTUATION.sub(" ", lowered.replace("'", ""))
    return _WHITESPACE.sub(" ", without_punctuation).strip()


def _contains_any(value: str, *needles: str) -> bool:
    return any(needle.replace("'", "") in value for needle in needles)


def _extract_id(value: str, label: str) -> int | None:
    match = re.search(rf"\b{label}\s+#?(\d+)\b", value)
    if match is None:
        return None
    return int(match.group(1))
