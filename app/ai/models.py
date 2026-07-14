from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..graph.models import NodeType


class IntentType(StrEnum):
    EXPLAIN_ACCESS = "explain_access"
    ACCESS_GAP = "access_gap"
    PROVISIONING = "provisioning"
    REMEDIATION = "remediation"
    REVIEW = "review"
    ACCESS_PATH = "access_path"
    MANAGER_CHAIN = "manager_chain"
    GENERAL = "general"


class AIContextRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=1000,
        examples=["Why does user 1 have access to Salesforce?"],
        description="User question to classify and answer with deterministic context.",
    )
    user_id: int | None = Field(
        default=None,
        examples=[1],
        description="Optional AccessIQ user ID to anchor graph evidence.",
    )
    application_id: int | None = Field(
        default=None,
        examples=[1],
        description="Optional application ID to include application graph evidence.",
    )
    entitlement_id: int | None = Field(
        default=None,
        examples=[1],
        description="Optional entitlement ID to include entitlement graph evidence.",
    )
    source_type: NodeType | None = Field(
        default=None,
        description="Optional source node type for explicit path questions.",
    )
    source_id: str | None = Field(
        default=None,
        examples=["1"],
        description="Optional source record ID for explicit path questions.",
    )
    target_type: NodeType | None = Field(
        default=None,
        description="Optional target node type for explicit path questions.",
    )
    target_id: str | None = Field(
        default=None,
        examples=["1"],
        description="Optional target record ID for explicit path questions.",
    )
    max_tokens: int = Field(
        default=1200,
        ge=50,
        le=8000,
        description=(
            "Approximate total prompt budget. AccessIQ uses a deterministic "
            "character-count estimate rather than a tokenizer."
        ),
    )


class IntentClassification(BaseModel):
    intent: IntentType
    confidence: float = Field(ge=0, le=1)
    matched_rules: list[str]
    normalized_question: str
    user_id: int | None = None
    application_id: int | None = None
    entitlement_id: int | None = None


class AIEvidence(BaseModel):
    id: str
    evidence_type: str
    title: str
    description: str
    reference: str
    timestamp: datetime | None = None
    correlation_id: str | None = None
    relationship_type: str | None = None
    node_id: str | None = None
    edge_id: str | None = None
    distance: int | None = None
    priority: int = 0
    rank_score: int = 0
    token_estimate: int = 0


class Citation(BaseModel):
    id: str
    title: str
    reference: str
    correlation_id: str | None = None


class TokenBudget(BaseModel):
    max_tokens: int
    reserved_tokens: int
    evidence_tokens: int
    total_estimated_tokens: int
    included_evidence_count: int
    omitted_evidence_count: int
    truncated: bool


class AIContext(BaseModel):
    question: str
    intent: IntentClassification
    subject: dict[str, Any]
    evidence: list[AIEvidence]
    citations: list[Citation]
    token_budget: TokenBudget
    graph_summary: dict[str, int | str]


class AIEvidenceResponse(BaseModel):
    question: str
    intent: IntentClassification
    evidence: list[AIEvidence]
    citations: list[Citation]
    token_budget: TokenBudget


class PromptMessage(BaseModel):
    role: Literal["system", "user"]
    content: str


class StructuredPrompt(BaseModel):
    system_instructions: list[str]
    user_question: str
    assembled_evidence: list[AIEvidence]
    citations: list[Citation]
    constraints: list[str]
    messages: list[PromptMessage]


class AIPromptResponse(BaseModel):
    question: str
    intent: IntentClassification
    context: AIContext
    prompt: StructuredPrompt


class LLMProviderMetadata(BaseModel):
    name: str
    display_name: str
    enabled: bool
    available: bool
    supports_streaming: bool = False
    model: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class LLMProviderHealth(BaseModel):
    provider: str
    status: Literal[
        "healthy",
        "unavailable",
        "disabled",
        "configuration_missing",
        "error",
    ]
    message: str
    metadata: LLMProviderMetadata


class LLMGenerationResult(BaseModel):
    answer: str
    provider: str
    model: str | None = None
    citations: list[Citation]
    metadata: dict[str, Any] = Field(default_factory=dict)


class AIExplainRequest(AIContextRequest):
    provider: str | None = Field(
        default=None,
        examples=["mock"],
        description="Optional provider override. Defaults to configured LLM_PROVIDER.",
    )


class AIExplanationTiming(BaseModel):
    context_ms: float
    provider_ms: float
    total_ms: float


class AIExplanationResponse(BaseModel):
    answer: str
    citations: list[Citation]
    evidence: list[AIEvidence]
    provider: LLMProviderMetadata
    timing: AIExplanationTiming
    intent: IntentClassification
    context: AIContext


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class Conversation(BaseModel):
    conversation_id: str
    messages: list[ConversationMessage]
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AIChatRequest(AIExplainRequest):
    conversation_id: str | None = Field(
        default=None,
        description="Optional conversation ID. A new in-memory conversation is created when omitted.",
    )


class AIChatResponse(BaseModel):
    conversation_id: str
    message: ConversationMessage
    explanation: AIExplanationResponse
    conversation: Conversation


class AIProvidersResponse(BaseModel):
    configured_provider: str
    enabled: bool
    providers: list[LLMProviderHealth]
