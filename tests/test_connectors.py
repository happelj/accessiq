from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import ConnectorSettings, get_connector_settings
from app.connectors import (
    ConnectorOperation,
    ConnectorRegistry,
    ConnectorStatus,
    ProvisioningOrchestrator,
    RetryPolicy,
    build_connector_registry,
)
from app.connectors.exceptions import (
    ConfigurationError,
    ConnectorError,
    RateLimitError,
    TimeoutError as ConnectorTimeoutError,
    UnknownConnectorError,
    ValidationError,
)
from app.connectors.github import GitHubConnector
from app.connectors.mock import ConnectorSimulationMode
from app.connectors.orchestrator import (
    ACTION_CONNECTOR_SUCCESS,
    ACTION_PROVISIONING_COMPLETED,
)
from app.connectors.results import ConnectorHealthStatus, ConnectorResult
from app.connectors.salesforce import SalesforceConnector
from app.connectors.zendesk import ZendeskConnector
from app.database import SessionLocal
from app.domain.events import (
    ConnectorRetryScheduled,
    ConnectorSucceeded,
    ProvisioningCompleted,
    ProvisioningStarted,
)
from app.domain.publisher import clear_published_events, get_published_events
from app.main import app

client = TestClient(app)


def auth_headers(email: str = "alice@example.com") -> dict[str, str]:
    response = client.post(
        "/login",
        json={
            "email": email,
            "password": "Password123!",
        },
    )

    assert response.status_code == 200

    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def find_user_by_email(email: str) -> dict[str, Any]:
    response = client.get("/users")
    assert response.status_code == 200

    for user in response.json():
        if user["email"] == email:
            return user

    raise AssertionError(f"User with email {email!r} was not found")


def test_registry_registration_and_lookup() -> None:
    registry = ConnectorRegistry()
    connector = SalesforceConnector()

    registry.register(connector)

    assert registry.exists(" SALESFORCE ")
    assert registry.get("salesforce") is connector


def test_registry_unknown_connector() -> None:
    registry = ConnectorRegistry()

    with pytest.raises(UnknownConnectorError):
        registry.get("unknown")


def test_registry_lists_connectors_sorted() -> None:
    registry = ConnectorRegistry([ZendeskConnector(), GitHubConnector()])

    assert [connector.name for connector in registry.list()] == [
        "github",
        "zendesk",
    ]


def test_registry_rejects_duplicate_connectors() -> None:
    registry = ConnectorRegistry([SalesforceConnector()])

    with pytest.raises(ConfigurationError):
        registry.register(SalesforceConnector())


def test_build_registry_respects_disabled_configuration() -> None:
    settings = ConnectorSettings(
        enable_salesforce_connector=False,
        enable_github_connector=True,
        enable_zendesk_connector=False,
        enable_finance_connector=False,
        salesforce_api_base_url=None,
        github_api_base_url=None,
        zendesk_api_base_url=None,
        finance_api_base_url=None,
    )

    registry = build_connector_registry(settings)

    assert registry.exists("github")
    assert not registry.exists("salesforce")
    assert [connector.name for connector in registry.list()] == ["github"]


def test_successful_user_operations() -> None:
    connector = SalesforceConnector()

    create_result = connector.create_user({"email": "new@example.com"})
    update_result = connector.update_user("1", {"display_name": "New User"})
    disable_result = connector.disable_user("1")
    delete_result = connector.delete_user("1")

    assert create_result.status == ConnectorStatus.SUCCESS
    assert update_result.status == ConnectorStatus.SUCCESS
    assert disable_result.status == ConnectorStatus.SUCCESS
    assert delete_result.status == ConnectorStatus.SUCCESS


def test_successful_group_operations() -> None:
    connector = GitHubConnector()

    create_result = connector.create_group({"display_name": "Developers"})
    update_result = connector.update_group("1", {"display_name": "Platform"})
    add_result = connector.add_group_member("1", "2")
    remove_result = connector.remove_group_member("1", "2")
    delete_result = connector.delete_group("1")

    assert create_result.status == ConnectorStatus.SUCCESS
    assert update_result.status == ConnectorStatus.SUCCESS
    assert add_result.status == ConnectorStatus.SUCCESS
    assert remove_result.status == ConnectorStatus.SUCCESS
    assert delete_result.status == ConnectorStatus.SUCCESS


def test_successful_entitlement_operations() -> None:
    connector = ZendeskConnector()

    grant_result = connector.grant_entitlement("1", {"slug": "agent"})
    revoke_result = connector.revoke_entitlement("1", {"slug": "agent"})

    assert grant_result.status == ConnectorStatus.SUCCESS
    assert revoke_result.status == ConnectorStatus.SUCCESS


def test_validation_failure_simulation() -> None:
    connector = SalesforceConnector(
        simulation_mode=ConnectorSimulationMode.VALIDATION_FAILURE
    )

    with pytest.raises(ValidationError):
        connector.create_user({"email": "invalid@example.com"})


def test_timeout_simulation() -> None:
    connector = SalesforceConnector(simulation_mode=ConnectorSimulationMode.TIMEOUT)

    with pytest.raises(ConnectorTimeoutError):
        connector.create_user({"email": "timeout@example.com"})


def test_rate_limit_simulation() -> None:
    connector = SalesforceConnector(simulation_mode=ConnectorSimulationMode.RATE_LIMIT)

    with pytest.raises(RateLimitError) as exc:
        connector.create_user({"email": "rate-limit@example.com"})

    assert exc.value.retryable is True
    assert exc.value.retry_after_ms == 1000


def test_non_retryable_failure_simulation() -> None:
    connector = SalesforceConnector(
        simulation_mode=ConnectorSimulationMode.NON_RETRYABLE_FAILURE
    )

    with pytest.raises(ConnectorError) as exc:
        connector.create_user({"email": "failure@example.com"})

    assert exc.value.retryable is False


def test_retry_policy() -> None:
    policy = RetryPolicy(max_attempts=3, base_delay_ms=25, max_delay_ms=60)
    retryable_error = RateLimitError("rate limited")
    non_retryable_error = ConnectorError("failed")

    assert policy.should_retry(retryable_error, attempt=1)
    assert policy.next_delay_ms(attempt=1) == 25
    assert policy.next_delay_ms(attempt=3) == 60
    assert not policy.should_retry(retryable_error, attempt=3)
    assert not policy.should_retry(non_retryable_error, attempt=1)


def test_connector_result_serialization() -> None:
    result = ConnectorResult.success(
        connector="salesforce",
        operation=ConnectorOperation.CREATE_USER,
        message="Created",
        duration_ms=1.25,
        correlation_id="corr-1",
        details={"external_id": "abc"},
    )

    serialized = result.to_dict()

    assert serialized["connector"] == "salesforce"
    assert serialized["operation"] == "create_user"
    assert serialized["status"] == "SUCCESS"
    assert serialized["retryable"] is False
    assert serialized["details"] == {"external_id": "abc"}


def test_health_check_healthy() -> None:
    health = SalesforceConnector().health_check()

    assert health.status == ConnectorHealthStatus.HEALTHY
    assert health.connector == "salesforce"


def test_health_check_degraded() -> None:
    health = SalesforceConnector(
        simulation_mode=ConnectorSimulationMode.DEGRADED
    ).health_check()

    assert health.status == ConnectorHealthStatus.DEGRADED


def test_health_check_unavailable() -> None:
    health = SalesforceConnector(
        simulation_mode=ConnectorSimulationMode.UNAVAILABLE
    ).health_check()

    assert health.status == ConnectorHealthStatus.UNAVAILABLE


def test_orchestrator_execution_publishes_events() -> None:
    clear_published_events()
    registry = ConnectorRegistry([SalesforceConnector()])
    orchestrator = ProvisioningOrchestrator(registry=registry)

    result = orchestrator.execute(
        connector_name="salesforce",
        operation=ConnectorOperation.CREATE_USER,
        payload={"email": "orchestrated@example.com"},
        correlation_id="corr-success",
    )

    events = get_published_events()

    assert result.status == ConnectorStatus.SUCCESS
    assert any(isinstance(event, ProvisioningStarted) for event in events)
    assert any(isinstance(event, ConnectorSucceeded) for event in events)
    assert any(isinstance(event, ProvisioningCompleted) for event in events)


def test_orchestrator_retryable_failure() -> None:
    clear_published_events()
    registry = ConnectorRegistry(
        [
            SalesforceConnector(
                simulation_mode=ConnectorSimulationMode.RETRYABLE_FAILURE
            )
        ]
    )
    orchestrator = ProvisioningOrchestrator(
        registry=registry,
        retry_policy=RetryPolicy(max_attempts=2),
    )

    result = orchestrator.execute(
        connector_name="salesforce",
        operation=ConnectorOperation.CREATE_USER,
        payload={"email": "retry@example.com"},
        correlation_id="corr-retry-failure",
    )

    assert result.status == ConnectorStatus.RETRYABLE
    assert result.retryable is True
    assert any(
        isinstance(event, ConnectorRetryScheduled)
        for event in get_published_events()
    )


def test_orchestrator_success_after_retry() -> None:
    clear_published_events()
    registry = ConnectorRegistry(
        [SalesforceConnector(failures_before_success=1)]
    )
    orchestrator = ProvisioningOrchestrator(
        registry=registry,
        retry_policy=RetryPolicy(max_attempts=2),
    )

    result = orchestrator.execute(
        connector_name="salesforce",
        operation=ConnectorOperation.CREATE_USER,
        payload={"email": "retry-success@example.com"},
        correlation_id="corr-retry-success",
    )

    assert result.status == ConnectorStatus.SUCCESS
    assert any(
        isinstance(event, ConnectorRetryScheduled)
        for event in get_published_events()
    )


def test_orchestrator_non_retryable_failure() -> None:
    registry = ConnectorRegistry(
        [
            SalesforceConnector(
                simulation_mode=ConnectorSimulationMode.NON_RETRYABLE_FAILURE
            )
        ]
    )
    orchestrator = ProvisioningOrchestrator(registry=registry)

    result = orchestrator.execute(
        connector_name="salesforce",
        operation=ConnectorOperation.CREATE_USER,
        payload={"email": "failed@example.com"},
    )

    assert result.status == ConnectorStatus.FAILED
    assert result.retryable is False


def test_orchestrator_audit_integration() -> None:
    requester = find_user_by_email("alice@example.com")
    target = find_user_by_email("bob@example.com")
    registry = ConnectorRegistry([SalesforceConnector()])
    orchestrator = ProvisioningOrchestrator(registry=registry)

    with SessionLocal() as db:
        result = orchestrator.execute(
            connector_name="salesforce",
            operation=ConnectorOperation.GRANT_ENTITLEMENT,
            payload={
                "user_id": str(target["id"]),
                "entitlement": {"slug": "user"},
            },
            correlation_id="corr-audit",
            db=db,
            requester_id=requester["id"],
            target_user_id=target["id"],
        )
        db.commit()

    audit_response = client.get(
        "/audit-events",
        headers=auth_headers("alice@example.com"),
        params={
            "requester_id": requester["id"],
            "target_user_id": target["id"],
            "action": ACTION_CONNECTOR_SUCCESS,
            "result": "succeeded",
        },
    )
    completed_response = client.get(
        "/audit-events",
        headers=auth_headers("alice@example.com"),
        params={
            "requester_id": requester["id"],
            "target_user_id": target["id"],
            "action": ACTION_PROVISIONING_COMPLETED,
            "result": "succeeded",
        },
    )

    assert result.status == ConnectorStatus.SUCCESS
    assert audit_response.status_code == 200
    assert any(
        event["entitlement"] == "Connector Execution"
        for event in audit_response.json()
    )
    assert completed_response.status_code == 200
    assert completed_response.json()


def test_connector_endpoints_list_metadata_and_health() -> None:
    list_response = client.get(
        "/connectors",
        headers=auth_headers("alice@example.com"),
    )
    metadata_response = client.get(
        "/connectors/salesforce",
        headers=auth_headers("alice@example.com"),
    )
    health_response = client.get(
        "/connectors/salesforce/health",
        headers=auth_headers("alice@example.com"),
    )

    assert list_response.status_code == 200
    assert {connector["name"] for connector in list_response.json()} >= {
        "salesforce",
        "github",
        "zendesk",
        "finance",
    }
    assert metadata_response.status_code == 200
    assert metadata_response.json()["supported_operations"]
    assert health_response.status_code == 200
    assert health_response.json()["status"] == "HEALTHY"


def test_connector_endpoints_require_rbac() -> None:
    unauthenticated_response = client.get("/connectors")
    employee_response = client.get(
        "/connectors",
        headers=auth_headers("bob@example.com"),
    )

    assert unauthenticated_response.status_code == 401
    assert employee_response.status_code == 403


def test_connector_endpoint_unknown_connector() -> None:
    response = client.get(
        "/connectors/not-real",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Connector not found"}


def test_connector_openapi_metadata() -> None:
    schema = client.get("/openapi.json").json()

    assert "/connectors" in schema["paths"]
    assert "/connectors/{name}" in schema["paths"]
    assert "/connectors/{name}/health" in schema["paths"]


def test_environment_configuration_enable_disable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_SALESFORCE_CONNECTOR", "false")
    monkeypatch.setenv("ENABLE_GITHUB_CONNECTOR", "true")
    monkeypatch.setenv("ENABLE_ZENDESK_CONNECTOR", "false")
    monkeypatch.setenv("ENABLE_FINANCE_CONNECTOR", "false")
    get_connector_settings.cache_clear()

    try:
        registry = build_connector_registry()
        assert not registry.exists("salesforce")
        assert registry.exists("github")
        assert [connector.name for connector in registry.list()] == ["github"]
    finally:
        get_connector_settings.cache_clear()
