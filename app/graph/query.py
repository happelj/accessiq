from __future__ import annotations

from .evidence import EvidenceBuilder
from .models import (
    AuthorizationGraph,
    EdgeType,
    EvidenceItem,
    GraphNode,
    GraphNodeDetail,
    GraphPath,
    GraphUserAccess,
    NodeType,
    graph_node_id,
)


class AuthorizationGraphQueryEngine:
    def __init__(self, graph: AuthorizationGraph) -> None:
        self.graph = graph
        self.evidence = EvidenceBuilder(graph)

    def find_user(self, user_id: int) -> GraphNode | None:
        return self.graph.get_node(graph_node_id(NodeType.USER, user_id))

    def find_group(self, group_id: int) -> GraphNode | None:
        return self.graph.get_node(graph_node_id(NodeType.GROUP, group_id))

    def find_application(self, application_id: int) -> GraphNode | None:
        return self.graph.get_node(graph_node_id(NodeType.APPLICATION, application_id))

    def find_entitlements(self, user_id: int) -> list[GraphNode]:
        user_node_id = graph_node_id(NodeType.USER, user_id)
        return [
            node
            for edge in self.graph.outgoing(user_node_id, EdgeType.HAS_ENTITLEMENT)
            if (node := self.graph.get_node(edge.target)) is not None
        ]

    def find_access_path(self, user_id: int, entitlement_id: int) -> GraphPath:
        return self.shortest_path(
            NodeType.USER,
            user_id,
            NodeType.ENTITLEMENT,
            entitlement_id,
        )

    def find_manager_chain(self, user_id: int) -> list[GraphNode]:
        chain: list[GraphNode] = []
        current = graph_node_id(NodeType.USER, user_id)
        seen = {current}

        while True:
            manager_edges = self.graph.outgoing(current, EdgeType.MANAGED_BY)
            if not manager_edges:
                return chain

            next_node_id = manager_edges[0].target
            if next_node_id in seen:
                return chain

            seen.add(next_node_id)
            node = self.graph.get_node(next_node_id)
            if node is None:
                return chain

            chain.append(node)
            current = next_node_id

    def find_review_history(self, user_id: int) -> list[GraphNode]:
        user_node_id = graph_node_id(NodeType.USER, user_id)
        return [
            node
            for edge in self.graph.outgoing(user_node_id, EdgeType.REVIEWED_IN)
            if (node := self.graph.get_node(edge.target)) is not None
            and node.type == NodeType.REVIEW_ITEM
        ]

    def find_provisioning_history(self, user_id: int) -> list[GraphNode]:
        job_nodes = [
            node
            for node in self.graph.nodes.values()
            if node.type == NodeType.PROVISIONING_JOB
            and node.properties.get("target_type") in {"user", "entitlement"}
            and str(node.properties.get("target_id")) == str(user_id)
        ]
        job_ids = {node.properties["source_id"] for node in job_nodes}
        return [
            node
            for node in self.graph.nodes.values()
            if node.type == NodeType.PROVISIONING_HISTORY
            and node.properties.get("job_id") in job_ids
        ]

    def find_remediation_history(self, user_id: int) -> list[GraphNode]:
        review_item_ids = {
            node.properties["source_id"] for node in self.find_review_history(user_id)
        }
        return [
            node
            for node in self.graph.nodes.values()
            if node.type == NodeType.REMEDIATION_JOB
            and node.properties.get("review_item_id") in review_item_ids
        ]

    def find_delegations(self, user_id: int) -> list[GraphNode]:
        user_node_id = graph_node_id(NodeType.USER, user_id)
        return [
            node
            for edge in self.graph.outgoing(user_node_id, EdgeType.DELEGATED_TO)
            if (node := self.graph.get_node(edge.target)) is not None
        ]

    def shortest_path(
        self,
        source_type: NodeType,
        source_id: int | str,
        target_type: NodeType,
        target_id: int | str,
    ) -> GraphPath:
        return self.graph.shortest_path(
            graph_node_id(source_type, source_id),
            graph_node_id(target_type, target_id),
        )

    def node_detail(self, node: GraphNode) -> GraphNodeDetail:
        return GraphNodeDetail(
            node=node,
            edges=self.graph.edges_for(node.id),
            evidence=self.evidence.node_evidence(node),
        )

    def user_access(self, user_id: int) -> GraphUserAccess | None:
        user = self.find_user(user_id)
        if user is None:
            return None

        entitlements = self.find_entitlements(user_id)
        return GraphUserAccess(
            user=user,
            entitlements=entitlements,
            paths=[
                self.find_access_path(user_id, entitlement.properties["source_id"])
                for entitlement in entitlements
            ],
            evidence=self.evidence.access_evidence(user_id),
        )

    def user_evidence(self, user_id: int) -> list[EvidenceItem]:
        return self.evidence.user_evidence(user_id)
