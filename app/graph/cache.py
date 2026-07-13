from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock

from sqlalchemy.orm import Session

from ..connectors.registry import ConnectorRegistry
from .builder import build_authorization_graph
from .models import AuthorizationGraph, GraphCacheStatus


class AuthorizationGraphCache:
    def __init__(self) -> None:
        self._graph: AuthorizationGraph | None = None
        self._loaded_at: datetime | None = None
        self._valid = False
        self._version = 0
        self._lock = Lock()

    def load(
        self,
        db: Session,
        *,
        registry: ConnectorRegistry,
    ) -> AuthorizationGraph:
        with self._lock:
            if self._graph is not None and self._valid:
                return self._graph

            return self._refresh_locked(db, registry=registry)

    def refresh(
        self,
        db: Session,
        *,
        registry: ConnectorRegistry,
    ) -> AuthorizationGraph:
        with self._lock:
            return self._refresh_locked(db, registry=registry)

    def invalidate(self) -> None:
        with self._lock:
            self._valid = False

    def status(self) -> GraphCacheStatus:
        with self._lock:
            graph = self._graph
            return GraphCacheStatus(
                loaded=graph is not None,
                valid=self._valid,
                node_count=len(graph.nodes) if graph is not None else 0,
                edge_count=len(graph.edges) if graph is not None else 0,
                version=self._version,
                loaded_at=self._loaded_at,
            )

    def _refresh_locked(
        self,
        db: Session,
        *,
        registry: ConnectorRegistry,
    ) -> AuthorizationGraph:
        self._graph = build_authorization_graph(db, registry=registry)
        self._loaded_at = datetime.now(UTC)
        self._valid = True
        self._version += 1
        return self._graph


graph_cache = AuthorizationGraphCache()
