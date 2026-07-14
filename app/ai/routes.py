from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .config import AISettings, get_ai_settings
from ..graph.query import AuthorizationGraphQueryEngine
from ..graph.routes import GRAPH_ROLES, get_graph_query_engine
from ..models import User
from ..rbac import require_roles
from .context import AIContextAssembler
from .conversation import conversation_store
from .explanation import (
    AIExplanationError,
    AIExplanationService,
)
from .models import (
    AIChatRequest,
    AIChatResponse,
    AIContext,
    AIContextRequest,
    AIEvidenceResponse,
    AIExplainRequest,
    AIExplanationResponse,
    AIPromptResponse,
    AIProvidersResponse,
)
from .prompt import build_prompt
from .providers import build_provider_registry
from .providers.base import LLMProvider

router = APIRouter(prefix="/ai", tags=["AI Context"])


def get_context_assembler(
    engine: AuthorizationGraphQueryEngine = Depends(get_graph_query_engine),
) -> AIContextAssembler:
    return AIContextAssembler(engine)


def get_llm_providers(
    settings: AISettings = Depends(get_ai_settings),
) -> dict[str, LLMProvider]:
    return build_provider_registry(settings)


def get_explanation_service(
    assembler: AIContextAssembler = Depends(get_context_assembler),
    providers: dict[str, LLMProvider] = Depends(get_llm_providers),
    settings: AISettings = Depends(get_ai_settings),
) -> AIExplanationService:
    return AIExplanationService(
        assembler=assembler,
        providers=providers,
        settings=settings,
        conversations=conversation_store,
    )


@router.post(
    "/context",
    response_model=AIContext,
    summary="Assemble deterministic AI context",
    description=(
        "Classifies a question, queries the authorization graph, ranks evidence, "
        "and applies an approximate token budget without calling an LLM."
    ),
)
def assemble_context(
    request: AIContextRequest,
    current_user: User = Depends(require_roles(*GRAPH_ROLES)),
    assembler: AIContextAssembler = Depends(get_context_assembler),
) -> AIContext:
    del current_user
    return assembler.assemble(request)


@router.post(
    "/evidence",
    response_model=AIEvidenceResponse,
    summary="Collect deterministic AI evidence",
    description="Returns ranked, deduplicated graph evidence for a question.",
)
def assemble_evidence(
    request: AIContextRequest,
    current_user: User = Depends(require_roles(*GRAPH_ROLES)),
    assembler: AIContextAssembler = Depends(get_context_assembler),
) -> AIEvidenceResponse:
    del current_user
    context = assembler.assemble(request)
    return AIEvidenceResponse(
        question=context.question,
        intent=context.intent,
        evidence=context.evidence,
        citations=context.citations,
        token_budget=context.token_budget,
    )


@router.post(
    "/prompt",
    response_model=AIPromptResponse,
    summary="Build a structured future-LLM prompt",
    description=(
        "Builds a prompt object from deterministic context. This endpoint does "
        "not call OpenAI, Anthropic, embeddings, pgvector, or semantic search."
    ),
)
def assemble_prompt(
    request: AIContextRequest,
    current_user: User = Depends(require_roles(*GRAPH_ROLES)),
    assembler: AIContextAssembler = Depends(get_context_assembler),
) -> AIPromptResponse:
    del current_user
    context = assembler.assemble(request)
    return AIPromptResponse(
        question=context.question,
        intent=context.intent,
        context=context,
        prompt=build_prompt(context),
    )


@router.post(
    "/explain",
    response_model=AIExplanationResponse,
    summary="Generate a grounded AI explanation",
    description=(
        "Runs deterministic context assembly and asks the configured provider "
        "to explain only the supplied evidence. The provider may not make "
        "authorization, provisioning, review, remediation, or policy decisions."
    ),
)
def explain(
    request: AIExplainRequest,
    current_user: User = Depends(require_roles(*GRAPH_ROLES)),
    service: AIExplanationService = Depends(get_explanation_service),
) -> AIExplanationResponse:
    del current_user
    try:
        return service.explain(request)
    except AIExplanationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post(
    "/chat",
    response_model=AIChatResponse,
    summary="Continue a grounded AI explanation conversation",
    description=(
        "Stores an in-memory conversation and returns an explanation grounded "
        "in deterministic graph evidence."
    ),
)
def chat(
    request: AIChatRequest,
    current_user: User = Depends(require_roles(*GRAPH_ROLES)),
    service: AIExplanationService = Depends(get_explanation_service),
) -> AIChatResponse:
    del current_user
    try:
        return service.chat(request)
    except AIExplanationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get(
    "/providers",
    response_model=AIProvidersResponse,
    summary="List configured AI providers",
    description="Returns provider health and metadata without making an LLM call.",
)
def list_providers(
    current_user: User = Depends(require_roles(*GRAPH_ROLES)),
    providers: dict[str, LLMProvider] = Depends(get_llm_providers),
    settings: AISettings = Depends(get_ai_settings),
) -> AIProvidersResponse:
    del current_user
    return AIProvidersResponse(
        configured_provider=settings.provider,
        enabled=settings.enabled,
        providers=[
            provider.health()
            for provider in sorted(
                providers.values(),
                key=lambda item: item.provider_name(),
            )
        ],
    )
