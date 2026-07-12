from __future__ import annotations

from collections.abc import Iterable

from ..config import ConnectorSettings, get_connector_settings
from .base import IdentityConnector
from .exceptions import ConfigurationError, UnknownConnectorError
from .finance import FinanceConnector
from .github import GitHubConnector
from .salesforce import SalesforceConnector
from .zendesk import ZendeskConnector


class ConnectorRegistry:
    def __init__(
        self,
        connectors: Iterable[IdentityConnector] | None = None,
    ) -> None:
        self._connectors: dict[str, IdentityConnector] = {}

        for connector in connectors or ():
            self.register(connector)

    def register(self, connector: IdentityConnector) -> None:
        name = normalize_connector_name(connector.name)
        if name in self._connectors:
            raise ConfigurationError(f"Connector {name!r} is already registered")

        self._connectors[name] = connector

    def get(self, name: str) -> IdentityConnector:
        normalized_name = normalize_connector_name(name)
        connector = self._connectors.get(normalized_name)
        if connector is None:
            raise UnknownConnectorError(name)

        return connector

    def list(self) -> list[IdentityConnector]:
        return [
            self._connectors[name]
            for name in sorted(self._connectors)
        ]

    def exists(self, name: str) -> bool:
        return normalize_connector_name(name) in self._connectors


def normalize_connector_name(name: str) -> str:
    return name.strip().lower()


def build_connector_registry(
    settings: ConnectorSettings | None = None,
) -> ConnectorRegistry:
    resolved_settings = settings or get_connector_settings()
    registry = ConnectorRegistry()

    if resolved_settings.enable_salesforce_connector:
        registry.register(SalesforceConnector())
    if resolved_settings.enable_github_connector:
        registry.register(GitHubConnector())
    if resolved_settings.enable_zendesk_connector:
        registry.register(ZendeskConnector())
    if resolved_settings.enable_finance_connector:
        registry.register(FinanceConnector())

    return registry
