from __future__ import annotations

from hashlib import sha1
from typing import Iterable

from ..graph.models import (
    EdgeType,
    EvidenceItem,
    GraphEdge,
    GraphNode,
    GraphPath,
    NodeType,
    graph_node_id,
)
from ..graph.query import AuthorizationGraphQueryEngine
from .models import AIContextRequest, AIEvidence, IntentClassification, IntentType

_EDGE_TYPE_VALUES = {edge_type.value for edge_type in EdgeType}


def collect_evidence(
    request: AIContextRequest,
    classification: IntentClassification,
    engine: AuthorizationGraphQueryEngine,
) -> list[AIEvidence]:
    evidence: list[AIEvidence] = []
    user_id = classification.user_id
    application_id = classification.application_id
    entitlement_id = classification.entitlement_id

    if user_id is not None:
        evidence.extend(_user_evidence(engine, user_id))

    if application_id is not None:
        evidence.extend(
            _node_detail_evidence(
                engine,
                graph_node_id(NodeType.APPLICATION, application_id),
                distance=1,
            )
        )

    if entitlement_id is not None:
        evidence.extend(
            _node_detail_evidence(
                engine,
                graph_node_id(NodeType.ENTITLEMENT, entitlement_id),
                distance=1,
            )
        )

    if classification.intent == IntentType.ACCESS_PATH:
        evidence.extend(_path_evidence(request, classification, engine))
    elif classification.intent == IntentType.ACCESS_GAP:
        evidence.extend(_access_gap_evidence(request, classification, engine))
    elif classification.intent == IntentType.MANAGER_CHAIN and user_id is not None:
        evidence.extend(_manager_chain_evidence(engine, user_id))
    elif classification.intent == IntentType.PROVISIONING and user_id is not None:
        evidence.extend(_history_evidence(engine.find_provisioning_history(user_id)))
    elif classification.intent == IntentType.REMEDIATION and user_id is not None:
        evidence.extend(_history_evidence(engine.find_remediation_history(user_id)))
    elif classification.intent == IntentType.REVIEW and user_id is not None:
        evidence.extend(_history_evidence(engine.find_review_history(user_id)))
    elif classification.intent == IntentType.EXPLAIN_ACCESS and user_id is not None:
        access = engine.user_access(user_id)
        if access is not None:
            for path in access.paths:
                evidence.extend(_graph_path_evidence(engine, path, distance=1))

    return deduplicate_evidence(evidence)


def deduplicate_evidence(evidence: Iterable[AIEvidence]) -> list[AIEvidence]:
    deduplicated: dict[tuple[str, str, str, str, str | None], AIEvidence] = {}

    for item in evidence:
        key = (
            item.evidence_type,
            item.title,
            item.description,
            item.reference,
            item.correlation_id,
        )
        existing = deduplicated.get(key)
        if existing is None:
            deduplicated[key] = item
            continue

        existing_distance = existing.distance if existing.distance is not None else 9999
        item_distance = item.distance if item.distance is not None else 9999
        if item.priority > existing.priority or item_distance < existing_distance:
            deduplicated[key] = item

    return sorted(deduplicated.values(), key=lambda item: item.id)


def _user_evidence(
    engine: AuthorizationGraphQueryEngine,
    user_id: int,
) -> list[AIEvidence]:
    return [
        _from_graph_evidence(item, distance=0) for item in engine.user_evidence(user_id)
    ]


def _node_detail_evidence(
    engine: AuthorizationGraphQueryEngine,
    node_id: str,
    *,
    distance: int,
) -> list[AIEvidence]:
    node = engine.graph.get_node(node_id)
    if node is None:
        return []
    return [
        _from_graph_evidence(item, distance=distance, node=node)
        for item in engine.node_detail(node).evidence
    ]


def _history_evidence(nodes: list[GraphNode]) -> list[AIEvidence]:
    return [_from_node(node, distance=1, priority=70) for node in nodes]


def _manager_chain_evidence(
    engine: AuthorizationGraphQueryEngine,
    user_id: int,
) -> list[AIEvidence]:
    manager_nodes = engine.find_manager_chain(user_id)
    if not manager_nodes:
        return [
            _synthetic_evidence(
                evidence_type="QUERY_RESULT",
                title="No manager chain found",
                description=f"User {user_id} has no manager chain in the authorization graph.",
                reference=f"/graph/users/{user_id}",
                priority=65,
            )
        ]

    return [
        _from_node(node, distance=index + 1, priority=75)
        for index, node in enumerate(manager_nodes)
    ]


def _path_evidence(
    request: AIContextRequest,
    classification: IntentClassification,
    engine: AuthorizationGraphQueryEngine,
) -> list[AIEvidence]:
    path = _resolve_path(request, classification, engine)
    if path is None:
        return []
    return _graph_path_evidence(engine, path, distance=0)


def _access_gap_evidence(
    request: AIContextRequest,
    classification: IntentClassification,
    engine: AuthorizationGraphQueryEngine,
) -> list[AIEvidence]:
    path = _resolve_path(request, classification, engine)
    if path is None:
        return []

    result = "found" if path.found else "not found"
    evidence = [
        _synthetic_evidence(
            evidence_type="PATH_RESULT",
            title=f"Graph path {result}",
            description=(
                f"Path lookup from {path.source} to {path.target} returned "
                f"{result} using deterministic graph traversal."
            ),
            reference="/graph/path",
            priority=90,
        )
    ]
    evidence.extend(_graph_path_evidence(engine, path, distance=0))
    return evidence


def _resolve_path(
    request: AIContextRequest,
    classification: IntentClassification,
    engine: AuthorizationGraphQueryEngine,
) -> GraphPath | None:
    if (
        request.source_type is not None
        and request.source_id is not None
        and request.target_type is not None
        and request.target_id is not None
    ):
        return engine.shortest_path(
            request.source_type,
            request.source_id,
            request.target_type,
            request.target_id,
        )

    if classification.user_id is None:
        return None

    if classification.entitlement_id is not None:
        return engine.find_access_path(
            classification.user_id,
            classification.entitlement_id,
        )

    if classification.application_id is not None:
        return engine.shortest_path(
            NodeType.USER,
            classification.user_id,
            NodeType.APPLICATION,
            classification.application_id,
        )

    return None


def _graph_path_evidence(
    engine: AuthorizationGraphQueryEngine,
    path: GraphPath,
    *,
    distance: int,
) -> list[AIEvidence]:
    evidence: list[AIEvidence] = []
    for index, node in enumerate(path.nodes):
        evidence.append(_from_node(node, distance=distance + index, priority=60))
    for index, edge in enumerate(path.edges):
        evidence.append(
            _from_graph_evidence(
                engine.evidence.edge_evidence(edge),
                distance=distance + index,
                edge=edge,
                priority=80,
            )
        )
    return evidence


def _from_node(
    node: GraphNode,
    *,
    distance: int | None,
    priority: int,
) -> AIEvidence:
    return AIEvidence(
        id=_stable_id(node.type.value, node.reference, node.label, str(distance)),
        evidence_type=node.type.value,
        title=f"{node.type.value}: {node.label}",
        description=f"Graph node {node.id} exists in the authorization graph.",
        reference=node.reference,
        timestamp=node.timestamp,
        node_id=node.id,
        distance=distance,
        priority=priority,
    )


def _from_graph_evidence(
    item: EvidenceItem,
    *,
    distance: int | None,
    node: GraphNode | None = None,
    edge: GraphEdge | None = None,
    priority: int = 0,
) -> AIEvidence:
    relationship_type = item.type if item.type in _EDGE_TYPE_VALUES else None
    return AIEvidence(
        id=_stable_id(item.type, item.reference, item.title, item.correlation_id or ""),
        evidence_type=item.type,
        title=item.title,
        description=item.description,
        reference=item.reference,
        timestamp=item.timestamp,
        correlation_id=item.correlation_id,
        relationship_type=relationship_type,
        node_id=node.id if node is not None else None,
        edge_id=edge.id if edge is not None else None,
        distance=distance,
        priority=priority,
    )


def _synthetic_evidence(
    *,
    evidence_type: str,
    title: str,
    description: str,
    reference: str,
    priority: int,
) -> AIEvidence:
    return AIEvidence(
        id=_stable_id(evidence_type, reference, title, description),
        evidence_type=evidence_type,
        title=title,
        description=description,
        reference=reference,
        priority=priority,
        distance=0,
    )


def _stable_id(*parts: str) -> str:
    digest = sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"ai-evidence:{digest}"
