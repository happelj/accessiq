from __future__ import annotations

from fastapi import APIRouter, Depends

from ..graph.query import AuthorizationGraphQueryEngine
from ..graph.routes import GRAPH_ROLES, get_graph_query_engine
from ..models import User
from ..rbac import require_roles
from .context import AIContextAssembler
from .models import (
    AIContext,
    AIContextRequest,
    AIEvidenceResponse,
    AIPromptResponse,
)
from .prompt import build_prompt

router = APIRouter(prefix="/ai", tags=["AI Context"])


def get_context_assembler(
    engine: AuthorizationGraphQueryEngine = Depends(get_graph_query_engine),
) -> AIContextAssembler:
    return AIContextAssembler(engine)


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
