from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from .results import ConnectorHealth, ConnectorOperation, ConnectorResult


class IdentityConnector(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def display_name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def enabled(self) -> bool:
        raise NotImplementedError

    @property
    @abstractmethod
    def supported_operations(self) -> tuple[ConnectorOperation, ...]:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> ConnectorHealth:
        raise NotImplementedError

    @abstractmethod
    def create_user(
        self,
        user: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        raise NotImplementedError

    @abstractmethod
    def update_user(
        self,
        user_id: str,
        user: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        raise NotImplementedError

    @abstractmethod
    def disable_user(
        self,
        user_id: str,
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        raise NotImplementedError

    @abstractmethod
    def delete_user(
        self,
        user_id: str,
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        raise NotImplementedError

    @abstractmethod
    def create_group(
        self,
        group: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        raise NotImplementedError

    @abstractmethod
    def update_group(
        self,
        group_id: str,
        group: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        raise NotImplementedError

    @abstractmethod
    def delete_group(
        self,
        group_id: str,
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        raise NotImplementedError

    @abstractmethod
    def add_group_member(
        self,
        group_id: str,
        user_id: str,
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        raise NotImplementedError

    @abstractmethod
    def remove_group_member(
        self,
        group_id: str,
        user_id: str,
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        raise NotImplementedError

    @abstractmethod
    def grant_entitlement(
        self,
        user_id: str,
        entitlement: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        raise NotImplementedError

    @abstractmethod
    def revoke_entitlement(
        self,
        user_id: str,
        entitlement: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> ConnectorResult:
        raise NotImplementedError
