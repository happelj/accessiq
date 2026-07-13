from __future__ import annotations

from .budget import apply_token_budget, estimate_tokens
from .evidence import collect_evidence
from .intents import classify_intent
from .models import AIContext, AIContextRequest, Citation
from .ranking import rank_evidence

from ..graph.query import AuthorizationGraphQueryEngine


class AIContextAssembler:
    def __init__(self, engine: AuthorizationGraphQueryEngine) -> None:
        self.engine = engine

    def assemble(self, request: AIContextRequest) -> AIContext:
        classification = classify_intent(request)
        evidence = collect_evidence(request, classification, self.engine)
        ranked_evidence = rank_evidence(evidence, intent=classification.intent)
        reserved_tokens = min(
            request.max_tokens // 3,
            estimate_tokens(request.question) + 80,
        )
        budgeted_evidence, token_budget = apply_token_budget(
            ranked_evidence,
            max_tokens=request.max_tokens,
            reserved_tokens=reserved_tokens,
        )

        return AIContext(
            question=request.question,
            intent=classification,
            subject={
                "user_id": classification.user_id,
                "application_id": classification.application_id,
                "entitlement_id": classification.entitlement_id,
                "source_type": request.source_type,
                "source_id": request.source_id,
                "target_type": request.target_type,
                "target_id": request.target_id,
            },
            evidence=budgeted_evidence,
            citations=[
                Citation(
                    id=item.id,
                    title=item.title,
                    reference=item.reference,
                    correlation_id=item.correlation_id,
                )
                for item in budgeted_evidence
            ],
            token_budget=token_budget,
            graph_summary={
                "source": "authorization_graph",
                "node_count": len(self.engine.graph.nodes),
                "edge_count": len(self.engine.graph.edges),
            },
        )
