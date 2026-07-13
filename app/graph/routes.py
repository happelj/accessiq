from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ..connectors.registry import ConnectorRegistry
from ..database import get_db
from ..dependencies import get_connector_registry
from ..models import User
from ..rbac import require_roles
from .cache import AuthorizationGraphCache, graph_cache
from .export import export_graphviz_dot, export_json, export_mermaid
from .models import (
    EvidenceItem,
    GraphCacheStatus,
    GraphNodeDetail,
    GraphPath,
    GraphUserAccess,
    NodeType,
)
from .query import AuthorizationGraphQueryEngine

router = APIRouter(prefix="/graph", tags=["Authorization Graph"])

GRAPH_ROLES = ("security_admin", "iam_admin", "auditor")


def get_graph_cache() -> AuthorizationGraphCache:
    return graph_cache


def get_graph_query_engine(
    db: Session = Depends(get_db),
    registry: ConnectorRegistry = Depends(get_connector_registry),
    cache: AuthorizationGraphCache = Depends(get_graph_cache),
) -> AuthorizationGraphQueryEngine:
    return AuthorizationGraphQueryEngine(cache.load(db, registry=registry))


@router.get(
    "/cache/status",
    response_model=GraphCacheStatus,
    summary="Read authorization graph cache status",
)
def get_cache_status(
    current_user: User = Depends(require_roles(*GRAPH_ROLES)),
    cache: AuthorizationGraphCache = Depends(get_graph_cache),
) -> GraphCacheStatus:
    del current_user
    return cache.status()


@router.post(
    "/cache/refresh",
    response_model=GraphCacheStatus,
    summary="Refresh authorization graph cache",
)
def refresh_cache(
    current_user: User = Depends(require_roles(*GRAPH_ROLES)),
    db: Session = Depends(get_db),
    registry: ConnectorRegistry = Depends(get_connector_registry),
    cache: AuthorizationGraphCache = Depends(get_graph_cache),
) -> GraphCacheStatus:
    del current_user
    cache.refresh(db, registry=registry)
    return cache.status()


@router.post(
    "/cache/invalidate",
    response_model=GraphCacheStatus,
    summary="Invalidate authorization graph cache",
)
def invalidate_cache(
    current_user: User = Depends(require_roles(*GRAPH_ROLES)),
    cache: AuthorizationGraphCache = Depends(get_graph_cache),
) -> GraphCacheStatus:
    del current_user
    cache.invalidate()
    return cache.status()


@router.get(
    "/users/{user_id}",
    response_model=GraphNodeDetail,
    summary="Find a user graph node",
)
def find_user(
    user_id: int,
    current_user: User = Depends(require_roles(*GRAPH_ROLES)),
    engine: AuthorizationGraphQueryEngine = Depends(get_graph_query_engine),
) -> GraphNodeDetail:
    del current_user
    node = engine.find_user(user_id)
    if node is None:
        raise _not_found("Graph user node not found")
    return engine.node_detail(node)


@router.get(
    "/users/{user_id}/access",
    response_model=GraphUserAccess,
    summary="Find user access in the authorization graph",
)
def find_user_access(
    user_id: int,
    current_user: User = Depends(require_roles(*GRAPH_ROLES)),
    engine: AuthorizationGraphQueryEngine = Depends(get_graph_query_engine),
) -> GraphUserAccess:
    del current_user
    result = engine.user_access(user_id)
    if result is None:
        raise _not_found("Graph user node not found")
    return result


@router.get(
    "/users/{user_id}/evidence",
    response_model=list[EvidenceItem],
    summary="Build evidence for a user",
)
def find_user_evidence(
    user_id: int,
    current_user: User = Depends(require_roles(*GRAPH_ROLES)),
    engine: AuthorizationGraphQueryEngine = Depends(get_graph_query_engine),
) -> list[EvidenceItem]:
    del current_user
    evidence = engine.user_evidence(user_id)
    if not evidence and engine.find_user(user_id) is None:
        raise _not_found("Graph user node not found")
    return evidence


@router.get(
    "/groups/{group_id}",
    response_model=GraphNodeDetail,
    summary="Find a group graph node",
)
def find_group(
    group_id: int,
    current_user: User = Depends(require_roles(*GRAPH_ROLES)),
    engine: AuthorizationGraphQueryEngine = Depends(get_graph_query_engine),
) -> GraphNodeDetail:
    del current_user
    node = engine.find_group(group_id)
    if node is None:
        raise _not_found("Graph group node not found")
    return engine.node_detail(node)


@router.get(
    "/applications/{application_id}",
    response_model=GraphNodeDetail,
    summary="Find an application graph node",
)
def find_application(
    application_id: int,
    current_user: User = Depends(require_roles(*GRAPH_ROLES)),
    engine: AuthorizationGraphQueryEngine = Depends(get_graph_query_engine),
) -> GraphNodeDetail:
    del current_user
    node = engine.find_application(application_id)
    if node is None:
        raise _not_found("Graph application node not found")
    return engine.node_detail(node)


@router.get(
    "/path",
    response_model=GraphPath,
    summary="Find the shortest path between two graph nodes",
)
def find_shortest_path(
    source_type: NodeType = Query(
        ...,
        examples=["User"],
        description="Source graph node type.",
    ),
    source_id: str = Query(..., examples=["1"], description="Source record ID."),
    target_type: NodeType = Query(
        ...,
        examples=["Entitlement"],
        description="Target graph node type.",
    ),
    target_id: str = Query(..., examples=["1"], description="Target record ID."),
    current_user: User = Depends(require_roles(*GRAPH_ROLES)),
    engine: AuthorizationGraphQueryEngine = Depends(get_graph_query_engine),
) -> GraphPath:
    del current_user
    return engine.shortest_path(source_type, source_id, target_type, target_id)


@router.get(
    "/export",
    summary="Export the authorization graph",
    description="Exports the graph as JSON, Mermaid, or Graphviz DOT.",
)
def export_graph(
    export_format: Literal["json", "mermaid", "dot"] = Query(
        default="json",
        alias="format",
    ),
    current_user: User = Depends(require_roles(*GRAPH_ROLES)),
    db: Session = Depends(get_db),
    registry: ConnectorRegistry = Depends(get_connector_registry),
    cache: AuthorizationGraphCache = Depends(get_graph_cache),
):
    del current_user
    graph = cache.load(db, registry=registry)

    if export_format == "json":
        return export_json(graph)
    if export_format == "mermaid":
        return Response(export_mermaid(graph), media_type="text/plain")

    return Response(export_graphviz_dot(graph), media_type="text/vnd.graphviz")


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
