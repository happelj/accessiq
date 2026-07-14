from __future__ import annotations

from collections import deque
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class NodeType(StrEnum):
    USER = "User"
    GROUP = "Group"
    APPLICATION = "Application"
    ENTITLEMENT = "Entitlement"
    DELEGATION = "Delegation"
    CERTIFICATION_CAMPAIGN = "CertificationCampaign"
    REVIEW_ITEM = "ReviewItem"
    PROVISIONING_JOB = "ProvisioningJob"
    PROVISIONING_HISTORY = "ProvisioningHistory"
    REMEDIATION_JOB = "RemediationJob"
    AUDIT_EVENT = "AuditEvent"
    CONNECTOR = "Connector"
    ENTERPRISE_PROFILE = "EnterpriseProfile"


class EdgeType(StrEnum):
    MEMBER_OF = "MEMBER_OF"
    HAS_ENTITLEMENT = "HAS_ENTITLEMENT"
    GRANTS_ACCESS_TO = "GRANTS_ACCESS_TO"
    PROVISIONED_BY = "PROVISIONED_BY"
    REVIEWED_IN = "REVIEWED_IN"
    REMEDIATED_BY = "REMEDIATED_BY"
    MANAGED_BY = "MANAGED_BY"
    DELEGATED_TO = "DELEGATED_TO"
    CONNECTED_TO = "CONNECTED_TO"
    AUDITED_BY = "AUDITED_BY"


class GraphNode(BaseModel):
    id: str
    type: NodeType
    label: str
    reference: str
    properties: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | None = None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: EdgeType
    label: str
    reference: str
    properties: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | None = None
    correlation_id: str | None = None


class EvidenceItem(BaseModel):
    type: str
    title: str
    description: str
    reference: str
    timestamp: datetime | None = None
    correlation_id: str | None = None


class GraphNodeDetail(BaseModel):
    node: GraphNode
    edges: list[GraphEdge]
    evidence: list[EvidenceItem]


class GraphPath(BaseModel):
    source: str
    target: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    found: bool


class GraphUserAccess(BaseModel):
    user: GraphNode
    entitlements: list[GraphNode]
    paths: list[GraphPath]
    evidence: list[EvidenceItem]


class GraphCacheStatus(BaseModel):
    loaded: bool
    valid: bool
    node_count: int
    edge_count: int
    version: int
    loaded_at: datetime | None = None


class AuthorizationGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self._outgoing: dict[str, list[GraphEdge]] = {}
        self._incoming: dict[str, list[GraphEdge]] = {}

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.id] = node
        self._outgoing.setdefault(node.id, [])
        self._incoming.setdefault(node.id, [])

    def add_edge(
        self,
        *,
        source: str,
        target: str,
        edge_type: EdgeType,
        label: str,
        reference: str,
        properties: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
        correlation_id: str | None = None,
    ) -> GraphEdge:
        edge = GraphEdge(
            id=f"edge:{len(self.edges) + 1}",
            source=source,
            target=target,
            type=edge_type,
            label=label,
            reference=reference,
            properties=properties or {},
            timestamp=timestamp,
            correlation_id=correlation_id,
        )
        self.edges.append(edge)
        self._outgoing.setdefault(source, []).append(edge)
        self._incoming.setdefault(target, []).append(edge)
        return edge

    def get_node(self, node_id: str) -> GraphNode | None:
        return self.nodes.get(node_id)

    def edges_for(self, node_id: str) -> list[GraphEdge]:
        return sorted(
            [
                *self._outgoing.get(node_id, []),
                *self._incoming.get(node_id, []),
            ],
            key=lambda edge: edge.id,
        )

    def outgoing(
        self,
        node_id: str,
        edge_type: EdgeType | None = None,
    ) -> list[GraphEdge]:
        edges = self._outgoing.get(node_id, [])
        if edge_type is not None:
            edges = [edge for edge in edges if edge.type == edge_type]
        return sorted(edges, key=lambda edge: edge.id)

    def incoming(
        self,
        node_id: str,
        edge_type: EdgeType | None = None,
    ) -> list[GraphEdge]:
        edges = self._incoming.get(node_id, [])
        if edge_type is not None:
            edges = [edge for edge in edges if edge.type == edge_type]
        return sorted(edges, key=lambda edge: edge.id)

    def shortest_path(self, source: str, target: str) -> GraphPath:
        if source not in self.nodes or target not in self.nodes:
            return GraphPath(
                source=source, target=target, nodes=[], edges=[], found=False
            )

        queue: deque[tuple[str, list[str], list[GraphEdge]]] = deque(
            [(source, [source], [])]
        )
        visited = {source}

        while queue:
            current, path_nodes, path_edges = queue.popleft()
            if current == target:
                return GraphPath(
                    source=source,
                    target=target,
                    nodes=[self.nodes[node_id] for node_id in path_nodes],
                    edges=path_edges,
                    found=True,
                )

            for edge in self.edges_for(current):
                neighbor = edge.target if edge.source == current else edge.source
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                queue.append((neighbor, [*path_nodes, neighbor], [*path_edges, edge]))

        return GraphPath(source=source, target=target, nodes=[], edges=[], found=False)

    def export(self) -> dict[str, Any]:
        return {
            "nodes": [
                node.model_dump(mode="json")
                for node in sorted(self.nodes.values(), key=lambda item: item.id)
            ],
            "edges": [edge.model_dump(mode="json") for edge in self.edges],
        }


def graph_node_id(node_type: NodeType, source_id: int | str) -> str:
    return f"{node_type.value}:{source_id}"
