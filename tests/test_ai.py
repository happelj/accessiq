from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.ai import AIContextAssembler, AIContextRequest, AIEvidence, IntentType
from app.ai.budget import apply_token_budget
from app.ai.config import AISettings, get_ai_settings
from app.ai.evidence import deduplicate_evidence
from app.ai.intents import classify_intent
from app.ai.models import AIContext, Citation, IntentClassification, TokenBudget
from app.ai.prompt import build_prompt
from app.ai.providers.mock import MockLLMProvider
from app.ai.providers.openai import OpenAIProvider
from app.ai.providers.base import ProviderConfigurationError
from app.ai.ranking import rank_evidence
from app.connectors.registry import build_connector_registry
from app.database import SessionLocal
from app.graph import AuthorizationGraphQueryEngine, build_authorization_graph
from app.graph.models import EdgeType
from app.graph.routes import graph_cache
from app.main import app

client = TestClient(app)


@dataclass(frozen=True)
class AIFixture:
    run_id: str
    user_id: int
    application_id: int
    entitlement_id: int


@pytest.fixture(scope="module")
def ai_fixture() -> AIFixture:
    run_id = str(uuid4())
    admin_headers = auth_headers("alice@example.com")
    application = find_by(api_get("/applications"), "slug", "salesforce")
    entitlement = find_by(
        api_get(f"/applications/{application['id']}/entitlements"),
        "slug",
        "user",
    )
    user = api_post(
        "/users",
        {
            "name": "AI Context User",
            "email": f"ai-context-{run_id}@example.com",
            "department": "Sales",
            "active": True,
            "operator_role": "employee",
        },
    )

    api_post(
        "/access/grant",
        {
            "target_user_id": user["id"],
            "entitlement_id": entitlement["id"],
        },
        headers=admin_headers,
    )
    graph_cache.invalidate()

    return AIFixture(
        run_id=run_id,
        user_id=user["id"],
        application_id=application["id"],
        entitlement_id=entitlement["id"],
    )


def test_intent_classification_rules_are_deterministic() -> None:
    access = classify_intent(
        AIContextRequest(question="Why does user 12 have access?")
    )
    access_gap = classify_intent(
        AIContextRequest(question="Why can't user 12 access application 2?")
    )
    provisioning = classify_intent(
        AIContextRequest(question="Explain provisioning for user 3")
    )
    manager_chain = classify_intent(
        AIContextRequest(question="Show manager chain for user 4")
    )

    assert access.intent == IntentType.EXPLAIN_ACCESS
    assert access.user_id == 12
    assert "explain_access_phrase" in access.matched_rules
    assert access_gap.intent == IntentType.ACCESS_GAP
    assert access_gap.application_id == 2
    assert provisioning.intent == IntentType.PROVISIONING
    assert manager_chain.intent == IntentType.MANAGER_CHAIN


def test_evidence_deduplication_ranking_and_token_budgeting() -> None:
    duplicated_low_priority = AIEvidence(
        id="low",
        evidence_type=EdgeType.HAS_ENTITLEMENT.value,
        relationship_type=EdgeType.HAS_ENTITLEMENT.value,
        title="User has entitlement",
        description="Access assignment evidence " * 8,
        reference="/users/1/access",
        distance=2,
        priority=10,
    )
    duplicated_high_priority = duplicated_low_priority.model_copy(
        update={"id": "high", "priority": 95, "distance": 0}
    )
    review = AIEvidence(
        id="review",
        evidence_type=EdgeType.REVIEWED_IN.value,
        relationship_type=EdgeType.REVIEWED_IN.value,
        title="Review item",
        description="Review evidence " * 16,
        reference="/access-reviews/items/1",
        distance=1,
    )

    deduplicated = deduplicate_evidence(
        [duplicated_low_priority, duplicated_high_priority, review]
    )
    ranked = rank_evidence(deduplicated, intent=IntentType.EXPLAIN_ACCESS)
    budgeted, token_budget = apply_token_budget(
        ranked,
        max_tokens=70,
        reserved_tokens=10,
    )

    assert len(deduplicated) == 2
    assert ranked[0].title == "User has entitlement"
    assert ranked[0].priority >= 95
    assert token_budget.truncated is True
    assert token_budget.included_evidence_count == len(budgeted)
    assert token_budget.omitted_evidence_count > 0


def test_prompt_generation_is_structured_and_constrained() -> None:
    evidence = AIEvidence(
        id="evidence-1",
        evidence_type=EdgeType.HAS_ENTITLEMENT.value,
        title="User has entitlement",
        description="User 1 has entitlement 1.",
        reference="/users/1/access",
    )
    context = AIContext(
        question="Why does user 1 have access?",
        intent=IntentClassification(
            intent=IntentType.EXPLAIN_ACCESS,
            confidence=0.85,
            matched_rules=["explain_access_phrase"],
            normalized_question="why does user 1 have access",
            user_id=1,
        ),
        subject={"user_id": 1},
        evidence=[evidence],
        citations=[Citation(id=evidence.id, title=evidence.title, reference=evidence.reference)],
        token_budget=TokenBudget(
            max_tokens=500,
            reserved_tokens=100,
            evidence_tokens=25,
            total_estimated_tokens=125,
            included_evidence_count=1,
            omitted_evidence_count=0,
            truncated=False,
        ),
        graph_summary={"source": "authorization_graph", "node_count": 1, "edge_count": 1},
    )

    prompt = build_prompt(context)

    assert prompt.user_question == context.question
    assert prompt.assembled_evidence == [evidence]
    assert "Do not make authorization" in prompt.messages[0].content
    assert "reference=/users/1/access" in prompt.messages[1].content


def test_mock_provider_generates_grounded_explanations() -> None:
    evidence = AIEvidence(
        id="evidence-1",
        evidence_type=EdgeType.HAS_ENTITLEMENT.value,
        title="User has entitlement",
        description="User 1 has Salesforce User.",
        reference="/users/1/access",
    )
    context = AIContext(
        question="Why does user 1 have access?",
        intent=IntentClassification(
            intent=IntentType.EXPLAIN_ACCESS,
            confidence=0.85,
            matched_rules=["explain_access_phrase"],
            normalized_question="why does user 1 have access",
            user_id=1,
        ),
        subject={"user_id": 1},
        evidence=[evidence],
        citations=[Citation(id=evidence.id, title=evidence.title, reference=evidence.reference)],
        token_budget=TokenBudget(
            max_tokens=500,
            reserved_tokens=100,
            evidence_tokens=25,
            total_estimated_tokens=125,
            included_evidence_count=1,
            omitted_evidence_count=0,
            truncated=False,
        ),
        graph_summary={"source": "authorization_graph", "node_count": 1, "edge_count": 1},
    )

    result = MockLLMProvider().generate(
        build_prompt(context),
        timeout_seconds=1,
        max_tokens=500,
    )

    assert result.provider == "mock"
    assert "Based only on deterministic AccessIQ evidence" in result.answer
    assert "No authorization decision was made" not in result.answer
    assert result.citations[0].reference == "/users/1/access"


def test_optional_openai_provider_reports_missing_configuration() -> None:
    provider = OpenAIProvider(
        AISettings(
            enabled=True,
            provider="openai",
            openai_api_key=None,
            anthropic_api_key=None,
            timeout_seconds=30,
            max_tokens=1200,
            openai_model="gpt-test",
            anthropic_model="claude-test",
        )
    )

    assert provider.health().status == "configuration_missing"
    assert provider.metadata().available is False
    with pytest.raises(ProviderConfigurationError):
        provider.generate(
            build_prompt(empty_context()),
            timeout_seconds=1,
            max_tokens=100,
        )


def test_ai_configuration_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "false")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("AI_TIMEOUT", "9")
    monkeypatch.setenv("AI_MAX_TOKENS", "321")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    get_ai_settings.cache_clear()

    settings = get_ai_settings()

    assert settings.enabled is False
    assert settings.provider == "anthropic"
    assert settings.timeout_seconds == 9
    assert settings.max_tokens == 321
    assert settings.openai_api_key == "openai-key"
    assert settings.anthropic_api_key == "anthropic-key"
    get_ai_settings.cache_clear()


def test_context_assembly_uses_authorization_graph(ai_fixture: AIFixture) -> None:
    assembler = AIContextAssembler(build_graph_engine())

    context = assembler.assemble(
        AIContextRequest(
            question="Why does this user have access?",
            user_id=ai_fixture.user_id,
            entitlement_id=ai_fixture.entitlement_id,
            max_tokens=1000,
        )
    )

    assert context.intent.intent == IntentType.EXPLAIN_ACCESS
    assert context.graph_summary["node_count"] > 0
    assert context.graph_summary["edge_count"] > 0
    assert any(
        item.evidence_type == EdgeType.HAS_ENTITLEMENT.value
        for item in context.evidence
    )
    assert context.citations


def test_ai_context_evidence_and_prompt_endpoints(ai_fixture: AIFixture) -> None:
    headers = auth_headers("alice@example.com")
    payload = {
        "question": "Why does this user have access to Salesforce?",
        "user_id": ai_fixture.user_id,
        "application_id": ai_fixture.application_id,
        "entitlement_id": ai_fixture.entitlement_id,
        "max_tokens": 1000,
    }

    context_response = client.post("/ai/context", headers=headers, json=payload)
    evidence_response = client.post("/ai/evidence", headers=headers, json=payload)
    prompt_response = client.post("/ai/prompt", headers=headers, json=payload)

    assert context_response.status_code == 200
    assert context_response.json()["intent"]["intent"] == IntentType.EXPLAIN_ACCESS.value
    assert context_response.json()["evidence"]
    assert evidence_response.status_code == 200
    assert evidence_response.json()["citations"]
    assert prompt_response.status_code == 200
    prompt = prompt_response.json()["prompt"]
    assert prompt["messages"][0]["role"] == "system"
    assert prompt["assembled_evidence"]


def test_ai_explain_chat_and_provider_endpoints(ai_fixture: AIFixture) -> None:
    headers = auth_headers("alice@example.com")
    payload = {
        "question": "Why does this user have access to Salesforce?",
        "user_id": ai_fixture.user_id,
        "application_id": ai_fixture.application_id,
        "entitlement_id": ai_fixture.entitlement_id,
        "provider": "mock",
        "max_tokens": 1000,
    }

    explain_response = client.post("/ai/explain", headers=headers, json=payload)
    chat_response = client.post("/ai/chat", headers=headers, json=payload)
    providers_response = client.get("/ai/providers", headers=headers)

    assert explain_response.status_code == 200
    explain = explain_response.json()
    assert explain["provider"]["name"] == "mock"
    assert "Based only on deterministic AccessIQ evidence" in explain["answer"]
    assert explain["citations"]
    assert explain["evidence"]
    assert explain["timing"]["total_ms"] >= 0

    assert chat_response.status_code == 200
    chat = chat_response.json()
    assert chat["conversation_id"]
    assert chat["message"]["role"] == "assistant"
    assert len(chat["conversation"]["messages"]) == 2

    assert providers_response.status_code == 200
    providers = providers_response.json()
    assert any(
        provider["provider"] == "mock" and provider["status"] == "healthy"
        for provider in providers["providers"]
    )


def test_ai_provider_unavailable_and_unknown_provider_errors(
    ai_fixture: AIFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = auth_headers("alice@example.com")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AI_ENABLED", "true")
    get_ai_settings.cache_clear()
    payload = {
        "question": "Why does this user have access?",
        "user_id": ai_fixture.user_id,
        "provider": "openai",
    }
    unavailable = client.post("/ai/explain", headers=headers, json=payload)
    unknown = client.post(
        "/ai/explain",
        headers=headers,
        json={**payload, "provider": "missing-provider"},
    )
    get_ai_settings.cache_clear()

    assert unavailable.status_code == 503
    assert "OPENAI_API_KEY" in unavailable.json()["detail"]
    assert unknown.status_code == 404


def test_ai_endpoints_require_authentication_and_rbac(
    ai_fixture: AIFixture,
) -> None:
    payload = {
        "question": "Why does this user have access?",
        "user_id": ai_fixture.user_id,
    }

    unauthenticated = client.post("/ai/context", json=payload)
    employee = client.post(
        "/ai/context",
        headers=auth_headers("bob@example.com"),
        json=payload,
    )
    auditor = client.post(
        "/ai/context",
        headers=auth_headers("auditor@example.com"),
        json=payload,
    )
    explain_employee = client.post(
        "/ai/explain",
        headers=auth_headers("bob@example.com"),
        json=payload,
    )
    providers_unauthenticated = client.get("/ai/providers")

    assert unauthenticated.status_code == 401
    assert employee.status_code == 403
    assert auditor.status_code == 200
    assert explain_employee.status_code == 403
    assert providers_unauthenticated.status_code == 401


def test_ai_openapi_metadata(ai_fixture: AIFixture) -> None:
    del ai_fixture
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    schemas = response.json()["components"]["schemas"]
    assert "/ai/context" in paths
    assert "/ai/evidence" in paths
    assert "/ai/prompt" in paths
    assert "/ai/explain" in paths
    assert "/ai/chat" in paths
    assert "/ai/providers" in paths
    assert "AIContext" in schemas
    assert "StructuredPrompt" in schemas
    assert "AIExplanationResponse" in schemas
    assert "AIChatResponse" in schemas
    assert "AIProvidersResponse" in schemas


def empty_context() -> AIContext:
    return AIContext(
        question="Why?",
        intent=IntentClassification(
            intent=IntentType.GENERAL,
            confidence=0.55,
            matched_rules=["fallback_general"],
            normalized_question="why",
        ),
        subject={},
        evidence=[],
        citations=[],
        token_budget=TokenBudget(
            max_tokens=100,
            reserved_tokens=50,
            evidence_tokens=0,
            total_estimated_tokens=50,
            included_evidence_count=0,
            omitted_evidence_count=0,
            truncated=False,
        ),
        graph_summary={"source": "authorization_graph", "node_count": 0, "edge_count": 0},
    )


def build_graph_engine() -> AuthorizationGraphQueryEngine:
    with SessionLocal() as db:
        graph = build_authorization_graph(db, registry=build_connector_registry())
    return AuthorizationGraphQueryEngine(graph)


def auth_headers(email: str) -> dict[str, str]:
    response = client.post(
        "/login",
        json={
            "email": email,
            "password": "Password123!",
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def api_get(path: str, headers: dict[str, str] | None = None):
    response = client.get(path, headers=headers)
    assert response.status_code == 200
    return response.json()


def api_post(
    path: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
):
    response = client.post(path, json=payload, headers=headers)
    assert response.status_code in {200, 201}, response.text
    return response.json()


def find_by(items: list[dict[str, Any]], key: str, value: Any) -> dict[str, Any]:
    for item in items:
        if item[key] == value:
            return item
    raise AssertionError(f"Could not find {key}={value!r}")
