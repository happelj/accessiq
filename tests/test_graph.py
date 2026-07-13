from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.connectors.registry import build_connector_registry
from app.database import SessionLocal
from app.graph import (
    AuthorizationGraphCache,
    AuthorizationGraphQueryEngine,
    EdgeType,
    NodeType,
    build_authorization_graph,
)
from app.graph.export import export_graphviz_dot, export_json, export_mermaid
from app.graph.models import graph_node_id
from app.graph.routes import graph_cache
from app.main import app

client = TestClient(app)

ENTERPRISE_EXTENSION = "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"


@dataclass(frozen=True)
class GraphFixture:
    run_id: str
    admin_id: int
    target_user_id: int
    manager_user_id: int
    group_id: int
    application_id: int
    entitlement_id: int
    delegate_user_id: int
    delegation_id: int
    campaign_id: int
    remediation_correlation_id: str


@pytest.fixture(scope="module")
def graph_fixture() -> GraphFixture:
    run_id = str(uuid4())
    admin_headers = auth_headers("alice@example.com")
    users = api_get("/users")
    admin = find_by(users, "email", "alice@example.com")
    manager = find_by(users, "email", "manager@example.com")
    application = find_by(api_get("/applications"), "slug", "salesforce")
    entitlement = find_by(
        api_get(f"/applications/{application['id']}/entitlements"),
        "slug",
        "user",
    )

    scim_user = api_post(
        "/scim/v2/Users",
        {
            "schemas": [
                "urn:ietf:params:scim:schemas:core:2.0:User",
                ENTERPRISE_EXTENSION,
            ],
            "userName": f"graph-user-{run_id}@example.com",
            "displayName": "Graph Test User",
            "active": True,
            ENTERPRISE_EXTENSION: {
                "employeeNumber": f"GRAPH-{run_id}",
                "department": "Engineering",
                "manager": {"value": str(manager["id"])},
            },
        },
        headers=admin_headers,
        content_type="application/scim+json",
    )
    target_user_id = int(scim_user["id"])

    group = api_post(
        "/scim/v2/Groups",
        {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
            "displayName": f"Graph Group {run_id}",
            "members": [{"value": str(target_user_id)}],
        },
        headers=admin_headers,
        content_type="application/scim+json",
    )

    delegate = api_post(
        "/users",
        {
            "name": "Graph Delegate",
            "email": f"graph-delegate-{run_id}@example.com",
            "department": "Operations",
            "active": True,
            "operator_role": "helpdesk",
        },
    )
    delegation = api_post(
        "/delegation/assignments",
        {
            "delegate_user_id": delegate["id"],
            "scope_type": "APPLICATION",
            "scope_id": application["id"],
            "delegation_role": "HELPDESK_DELEGATE",
        },
        headers=admin_headers,
    )

    api_post(
        "/access/grant",
        {
            "target_user_id": target_user_id,
            "entitlement_id": entitlement["id"],
        },
        headers=admin_headers,
    )

    campaign = api_post(
        "/access-reviews/campaigns",
        {
            "name": f"Graph Campaign {run_id}",
            "description": "Authorization graph test campaign",
            "reviewer_id": admin["id"],
        },
        headers=admin_headers,
    )
    started = api_post(
        f"/access-reviews/campaigns/{campaign['id']}/start",
        {},
        headers=admin_headers,
    )
    decide_all_review_items(
        campaign_id=campaign["id"],
        total_items=started["total_items"],
        target_user_id=target_user_id,
        entitlement_id=entitlement["id"],
        headers=admin_headers,
    )
    api_post(
        f"/access-reviews/campaigns/{campaign['id']}/complete",
        {},
        headers=admin_headers,
    )
    remediation = api_post(
        f"/access-reviews/campaigns/{campaign['id']}/remediate",
        {},
        headers=admin_headers,
    )

    graph_cache.invalidate()
    return GraphFixture(
        run_id=run_id,
        admin_id=admin["id"],
        target_user_id=target_user_id,
        manager_user_id=manager["id"],
        group_id=int(group["id"]),
        application_id=application["id"],
        entitlement_id=entitlement["id"],
        delegate_user_id=delegate["id"],
        delegation_id=delegation["id"],
        campaign_id=campaign["id"],
        remediation_correlation_id=remediation["jobs"][0]["correlation_id"],
    )


def test_graph_construction_contains_required_nodes_and_edges(
    graph_fixture: GraphFixture,
) -> None:
    graph = build_graph()

    required_nodes = {
        graph_node_id(NodeType.USER, graph_fixture.target_user_id),
        graph_node_id(NodeType.GROUP, graph_fixture.group_id),
        graph_node_id(NodeType.APPLICATION, graph_fixture.application_id),
        graph_node_id(NodeType.ENTITLEMENT, graph_fixture.entitlement_id),
        graph_node_id(NodeType.DELEGATION, graph_fixture.delegation_id),
        graph_node_id(NodeType.CERTIFICATION_CAMPAIGN, graph_fixture.campaign_id),
        graph_node_id(NodeType.CONNECTOR, "salesforce"),
    }
    assert required_nodes.issubset(graph.nodes)
    assert {
        NodeType.USER,
        NodeType.GROUP,
        NodeType.APPLICATION,
        NodeType.ENTITLEMENT,
        NodeType.DELEGATION,
        NodeType.CERTIFICATION_CAMPAIGN,
        NodeType.REVIEW_ITEM,
        NodeType.PROVISIONING_JOB,
        NodeType.PROVISIONING_HISTORY,
        NodeType.REMEDIATION_JOB,
        NodeType.AUDIT_EVENT,
        NodeType.CONNECTOR,
        NodeType.ENTERPRISE_PROFILE,
    }.issubset({node.type for node in graph.nodes.values()})
    assert any(edge.type == EdgeType.MEMBER_OF for edge in graph.edges)
    assert any(edge.type == EdgeType.HAS_ENTITLEMENT for edge in graph.edges)
    assert any(edge.type == EdgeType.REMEDIATED_BY for edge in graph.edges)
    assert any(edge.type == EdgeType.PROVISIONED_BY for edge in graph.edges)


def test_graph_cache_load_refresh_and_invalidate(
    graph_fixture: GraphFixture,
) -> None:
    cache = AuthorizationGraphCache()

    with SessionLocal() as db:
        first_graph = cache.load(db, registry=build_connector_registry())
        first_status = cache.status()
        second_graph = cache.load(db, registry=build_connector_registry())
        cache.invalidate()
        invalidated_status = cache.status()
        refreshed_graph = cache.refresh(db, registry=build_connector_registry())
        refreshed_status = cache.status()

    assert graph_node_id(NodeType.USER, graph_fixture.target_user_id) in first_graph.nodes
    assert second_graph is first_graph
    assert first_status.loaded is True
    assert first_status.valid is True
    assert invalidated_status.valid is False
    assert refreshed_graph is not first_graph
    assert refreshed_status.valid is True
    assert refreshed_status.version == 2


def test_query_engine_lookups_and_shortest_path(graph_fixture: GraphFixture) -> None:
    engine = AuthorizationGraphQueryEngine(build_graph())

    user = engine.find_user(graph_fixture.target_user_id)
    group = engine.find_group(graph_fixture.group_id)
    application = engine.find_application(graph_fixture.application_id)
    access = engine.user_access(graph_fixture.target_user_id)
    path = engine.find_access_path(
        graph_fixture.target_user_id,
        graph_fixture.entitlement_id,
    )

    assert user is not None
    assert group is not None
    assert application is not None
    assert access is not None
    assert [node.id for node in access.entitlements] == [
        graph_node_id(NodeType.ENTITLEMENT, graph_fixture.entitlement_id)
    ]
    assert path.found is True
    assert path.nodes[0].id == graph_node_id(NodeType.USER, graph_fixture.target_user_id)
    assert path.nodes[-1].id == graph_node_id(
        NodeType.ENTITLEMENT,
        graph_fixture.entitlement_id,
    )


def test_query_engine_manager_review_remediation_provisioning_and_delegations(
    graph_fixture: GraphFixture,
) -> None:
    engine = AuthorizationGraphQueryEngine(build_graph())

    manager_chain = engine.find_manager_chain(graph_fixture.target_user_id)
    review_history = engine.find_review_history(graph_fixture.target_user_id)
    remediation_history = engine.find_remediation_history(graph_fixture.target_user_id)
    provisioning_history = engine.find_provisioning_history(graph_fixture.target_user_id)
    delegations = engine.find_delegations(graph_fixture.delegate_user_id)

    assert [node.properties["source_id"] for node in manager_chain] == [
        graph_fixture.manager_user_id
    ]
    assert any(
        node.properties["campaign_id"] == graph_fixture.campaign_id
        for node in review_history
    )
    assert any(
        node.properties["correlation_id"] == graph_fixture.remediation_correlation_id
        for node in remediation_history
    )
    assert any(
        node.properties["correlation_id"] == graph_fixture.remediation_correlation_id
        for node in provisioning_history
    )
    assert [node.properties["source_id"] for node in delegations] == [
        graph_fixture.delegation_id
    ]


def test_evidence_generation(graph_fixture: GraphFixture) -> None:
    engine = AuthorizationGraphQueryEngine(build_graph())

    evidence = engine.user_evidence(graph_fixture.target_user_id)

    assert evidence
    assert any(item.type == EdgeType.HAS_ENTITLEMENT.value for item in evidence)
    assert any(item.type == EdgeType.MEMBER_OF.value for item in evidence)
    assert any(item.type == EdgeType.MANAGED_BY.value for item in evidence)


def test_graph_exports(graph_fixture: GraphFixture) -> None:
    graph = build_graph()

    json_export = export_json(graph)
    mermaid_export = export_mermaid(graph)
    dot_export = export_graphviz_dot(graph)

    assert graph_node_id(NodeType.USER, graph_fixture.target_user_id) in {
        node["id"] for node in json_export["nodes"]
    }
    assert "flowchart LR" in mermaid_export
    assert "HAS_ENTITLEMENT" in mermaid_export
    assert "digraph AuthorizationGraph" in dot_export
    assert "HAS_ENTITLEMENT" in dot_export


def test_graph_endpoints(graph_fixture: GraphFixture) -> None:
    headers = auth_headers("alice@example.com")
    api_post("/graph/cache/refresh", {}, headers=headers)

    user_response = client.get(
        f"/graph/users/{graph_fixture.target_user_id}",
        headers=headers,
    )
    access_response = client.get(
        f"/graph/users/{graph_fixture.target_user_id}/access",
        headers=headers,
    )
    evidence_response = client.get(
        f"/graph/users/{graph_fixture.target_user_id}/evidence",
        headers=headers,
    )
    group_response = client.get(
        f"/graph/groups/{graph_fixture.group_id}",
        headers=headers,
    )
    application_response = client.get(
        f"/graph/applications/{graph_fixture.application_id}",
        headers=headers,
    )
    path_response = client.get(
        "/graph/path",
        headers=headers,
        params={
            "source_type": "User",
            "source_id": graph_fixture.target_user_id,
            "target_type": "Entitlement",
            "target_id": graph_fixture.entitlement_id,
        },
    )

    assert user_response.status_code == 200
    assert access_response.status_code == 200
    assert evidence_response.status_code == 200
    assert group_response.status_code == 200
    assert application_response.status_code == 200
    assert path_response.status_code == 200
    assert path_response.json()["found"] is True


def test_graph_cache_endpoints(graph_fixture: GraphFixture) -> None:
    del graph_fixture
    headers = auth_headers("alice@example.com")

    invalidate_response = client.post("/graph/cache/invalidate", headers=headers)
    status_after_invalidate = client.get("/graph/cache/status", headers=headers)
    refresh_response = client.post("/graph/cache/refresh", headers=headers)

    assert invalidate_response.status_code == 200
    assert invalidate_response.json()["valid"] is False
    assert status_after_invalidate.status_code == 200
    assert status_after_invalidate.json()["valid"] is False
    assert refresh_response.status_code == 200
    assert refresh_response.json()["valid"] is True
    assert refresh_response.json()["node_count"] > 0
    assert refresh_response.json()["edge_count"] > 0


def test_graph_export_endpoints(graph_fixture: GraphFixture) -> None:
    del graph_fixture
    headers = auth_headers("alice@example.com")

    json_response = client.get("/graph/export?format=json", headers=headers)
    mermaid_response = client.get("/graph/export?format=mermaid", headers=headers)
    dot_response = client.get("/graph/export?format=dot", headers=headers)

    assert json_response.status_code == 200
    assert "nodes" in json_response.json()
    assert mermaid_response.status_code == 200
    assert "flowchart LR" in mermaid_response.text
    assert dot_response.status_code == 200
    assert "digraph AuthorizationGraph" in dot_response.text


def test_graph_endpoints_require_authentication_and_rbac(
    graph_fixture: GraphFixture,
) -> None:
    unauthenticated = client.get(f"/graph/users/{graph_fixture.target_user_id}")
    employee = client.get(
        f"/graph/users/{graph_fixture.target_user_id}",
        headers=auth_headers("bob@example.com"),
    )
    auditor = client.get(
        f"/graph/users/{graph_fixture.target_user_id}",
        headers=auth_headers("auditor@example.com"),
    )

    assert unauthenticated.status_code == 401
    assert employee.status_code == 403
    assert auditor.status_code == 200


def test_graph_openapi_metadata(graph_fixture: GraphFixture) -> None:
    del graph_fixture
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/graph/users/{user_id}" in paths
    assert "/graph/users/{user_id}/access" in paths
    assert "/graph/export" in paths
    assert "/graph/cache/refresh" in paths


def build_graph():
    with SessionLocal() as db:
        return build_authorization_graph(db, registry=build_connector_registry())


def decide_all_review_items(
    *,
    campaign_id: int,
    total_items: int,
    target_user_id: int,
    entitlement_id: int,
    headers: dict[str, str],
) -> None:
    items: list[dict[str, Any]] = []
    start_index = 1
    while len(items) < total_items:
        response = client.get(
            f"/access-reviews/campaigns/{campaign_id}/items",
            headers=headers,
            params={"start_index": start_index, "count": 500},
        )
        assert response.status_code == 200
        page = response.json()
        if not page:
            break
        items.extend(page)
        start_index += len(page)

    assert len(items) == total_items
    for item in items:
        decision = (
            "REVOKE"
            if item["user_id"] == target_user_id
            and item["entitlement_id"] == entitlement_id
            else "APPROVE"
        )
        response = client.post(
            f"/access-reviews/items/{item['id']}/decision",
            headers=headers,
            json={
                "decision": decision,
                "comments": f"Graph test {decision.lower()}",
            },
        )
        assert response.status_code == 200


def auth_headers(email: str) -> dict[str, str]:
    response = client.post(
        "/login",
        json={
            "email": email,
            "password": "Password123!",
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def api_get(path: str, headers: dict[str, str] | None = None):
    response = client.get(path, headers=headers)
    assert response.status_code == 200
    return response.json()


def api_post(
    path: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    content_type: str = "application/json",
):
    resolved_headers = dict(headers or {})
    resolved_headers["Content-Type"] = content_type
    response = client.post(path, json=payload, headers=resolved_headers)
    assert response.status_code in {200, 201}, response.text
    return response.json()


def find_by(items: list[dict[str, Any]], key: str, value: Any) -> dict[str, Any]:
    for item in items:
        if item[key] == value:
            return item
    raise AssertionError(f"Could not find {key}={value!r}")
