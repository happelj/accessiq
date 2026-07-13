from __future__ import annotations

from datetime import datetime

from ..graph.models import EdgeType
from .models import AIEvidence, IntentType


_BASE_PRIORITY = {
    EdgeType.HAS_ENTITLEMENT.value: 100,
    EdgeType.REVIEWED_IN.value: 80,
    EdgeType.REMEDIATED_BY.value: 80,
    EdgeType.PROVISIONED_BY.value: 75,
    EdgeType.MANAGED_BY.value: 70,
    EdgeType.DELEGATED_TO.value: 65,
    EdgeType.MEMBER_OF.value: 60,
    EdgeType.GRANTS_ACCESS_TO.value: 55,
    EdgeType.AUDITED_BY.value: 50,
    EdgeType.CONNECTED_TO.value: 40,
    "PATH_RESULT": 85,
    "QUERY_RESULT": 45,
}

_INTENT_BOOSTS = {
    IntentType.EXPLAIN_ACCESS: {
        EdgeType.HAS_ENTITLEMENT.value: 25,
        EdgeType.GRANTS_ACCESS_TO.value: 15,
        EdgeType.MEMBER_OF.value: 10,
    },
    IntentType.ACCESS_GAP: {
        "PATH_RESULT": 30,
        EdgeType.GRANTS_ACCESS_TO.value: 15,
        EdgeType.HAS_ENTITLEMENT.value: 15,
    },
    IntentType.PROVISIONING: {
        EdgeType.PROVISIONED_BY.value: 35,
        "ProvisioningJob": 25,
        "ProvisioningHistory": 25,
    },
    IntentType.REMEDIATION: {
        EdgeType.REMEDIATED_BY.value: 35,
        "RemediationJob": 25,
    },
    IntentType.REVIEW: {
        EdgeType.REVIEWED_IN.value: 35,
        "ReviewItem": 25,
        "CertificationCampaign": 20,
    },
    IntentType.ACCESS_PATH: {
        "PATH_RESULT": 35,
        EdgeType.HAS_ENTITLEMENT.value: 20,
        EdgeType.GRANTS_ACCESS_TO.value: 20,
    },
    IntentType.MANAGER_CHAIN: {
        EdgeType.MANAGED_BY.value: 35,
        "User": 10,
    },
}


def rank_evidence(
    evidence: list[AIEvidence],
    *,
    intent: IntentType,
) -> list[AIEvidence]:
    ranked = [
        item.model_copy(
            update={
                "priority": _priority_for(item, intent=intent),
                "rank_score": _score_for(item, intent=intent),
            }
        )
        for item in evidence
    ]
    return sorted(
        ranked,
        key=lambda item: (
            -item.rank_score,
            _timestamp_sort_value(item.timestamp),
            item.reference,
            item.title,
            item.id,
        ),
    )


def _priority_for(item: AIEvidence, *, intent: IntentType) -> int:
    evidence_type = item.relationship_type or item.evidence_type
    priority = item.priority or _BASE_PRIORITY.get(evidence_type, 35)
    priority += _INTENT_BOOSTS.get(intent, {}).get(evidence_type, 0)
    priority += _INTENT_BOOSTS.get(intent, {}).get(item.evidence_type, 0)
    return priority


def _score_for(item: AIEvidence, *, intent: IntentType) -> int:
    priority = _priority_for(item, intent=intent)
    distance_score = 0
    if item.distance is not None:
        distance_score = max(0, 25 - (item.distance * 5))

    timestamp_score = 10 if item.timestamp is not None else 0
    return priority + distance_score + timestamp_score


def _timestamp_sort_value(timestamp: datetime | None) -> float:
    if timestamp is None:
        return float("inf")
    return -timestamp.timestamp()
