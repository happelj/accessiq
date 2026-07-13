from __future__ import annotations

from .models import AIContext, PromptMessage, StructuredPrompt


SYSTEM_INSTRUCTIONS = [
    "Use only the assembled AccessIQ evidence supplied in this prompt.",
    "Do not make authorization, provisioning, governance, or policy decisions.",
    "Do not invent facts that are not present in the evidence.",
    "Cite evidence by reference when explaining graph relationships.",
]

CONSTRAINTS = [
    "The authorization graph is deterministic and read-only.",
    "The future LLM provider must not mutate AccessIQ state.",
    "Policy, provisioning, review, and remediation decisions remain outside AI.",
    "If evidence is insufficient, say what evidence is missing.",
]


def build_prompt(context: AIContext) -> StructuredPrompt:
    evidence_lines = [
        (
            f"[{index}] {item.title} | {item.description} | "
            f"reference={item.reference}"
        )
        for index, item in enumerate(context.evidence, start=1)
    ]
    evidence_text = "\n".join(evidence_lines) if evidence_lines else "No evidence."
    user_content = (
        f"Question: {context.question}\n"
        f"Intent: {context.intent.intent.value}\n\n"
        f"Evidence:\n{evidence_text}"
    )

    return StructuredPrompt(
        system_instructions=SYSTEM_INSTRUCTIONS,
        user_question=context.question,
        assembled_evidence=context.evidence,
        citations=context.citations,
        constraints=CONSTRAINTS,
        messages=[
            PromptMessage(
                role="system",
                content="\n".join([*SYSTEM_INSTRUCTIONS, *CONSTRAINTS]),
            ),
            PromptMessage(role="user", content=user_content),
        ],
    )
