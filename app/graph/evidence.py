from __future__ import annotations

from .models import (
    AuthorizationGraph,
    EdgeType,
    EvidenceItem,
    GraphEdge,
    GraphNode,
    NodeType,
)


class EvidenceBuilder:
    def __init__(self, graph: AuthorizationGraph) -> None:
        self.graph = graph

    def node_evidence(self, node: GraphNode) -> list[EvidenceItem]:
        evidence = [
            EvidenceItem(
                type=node.type.value,
                title=f"{node.type.value}: {node.label}",
                description=f"Graph node {node.id} exists in the authorization graph.",
                reference=node.reference,
                timestamp=node.timestamp,
            )
        ]
        evidence.extend(
            self.edge_evidence(edge)
            for edge in self.graph.edges_for(node.id)
        )
        return evidence

    def user_evidence(self, user_id: int) -> list[EvidenceItem]:
        node = self.graph.get_node(f"{NodeType.USER.value}:{user_id}")
        if node is None:
            return []
        return self.node_evidence(node)

    def edge_evidence(self, edge: GraphEdge) -> EvidenceItem:
        source = self.graph.get_node(edge.source)
        target = self.graph.get_node(edge.target)
        source_label = source.label if source is not None else edge.source
        target_label = target.label if target is not None else edge.target
        return EvidenceItem(
            type=edge.type.value,
            title=edge.label,
            description=(
                f"{source_label} --{edge.type.value}-> {target_label}"
            ),
            reference=edge.reference,
            timestamp=edge.timestamp,
            correlation_id=edge.correlation_id,
        )

    def access_evidence(self, user_id: int) -> list[EvidenceItem]:
        node_id = f"{NodeType.USER.value}:{user_id}"
        return [
            self.edge_evidence(edge)
            for edge in self.graph.outgoing(node_id, EdgeType.HAS_ENTITLEMENT)
        ]
