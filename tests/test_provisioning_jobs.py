from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.connectors import (
    ConnectorOperation,
    ConnectorRegistry,
    ConnectorStatus,
    ProvisioningOrchestrator,
    RetryPolicy,
)
from app.connectors.mock import ConnectorSimulationMode
from app.connectors.orchestrator import (
    ACTION_PROVISIONING_JOB_COMPLETED,
    ACTION_PROVISIONING_JOB_FAILED,
    ACTION_PROVISIONING_RETRY_RECORDED,
)
from app.connectors.salesforce import SalesforceConnector
from app.database import SessionLocal
from app.domain.events import (
    ProvisioningJobCompleted,
    ProvisioningJobCreated,
    ProvisioningJobFailed,
    ProvisioningRetryRecorded,
)
from app.domain.publisher import clear_published_events, get_published_events
from app.main import app
from app.services.provisioning_job_service import (
    ProvisioningHistoryEventType,
    ProvisioningJobFilters,
    ProvisioningJobService,
    ProvisioningJobStatus,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def ensure_database_initialized() -> None:
    response = client.get("/health")
    assert response.status_code == 200


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


def unique_correlation_id(prefix: str = "job") -> str:
    return f"{prefix}-{uuid4()}"


def test_job_creation() -> None:
    correlation_id = unique_correlation_id("create")

    with SessionLocal() as db:
        service = ProvisioningJobService(db)
        job = service.create_job(
            correlation_id=correlation_id,
            connector="salesforce",
            operation="create_user",
            target_type="user",
            target_id="job-create@example.com",
            max_attempts=3,
        )
        db.commit()
        job_id = job.id

    with SessionLocal() as db:
        service = ProvisioningJobService(db)
        job = service.lookup_job(job_id)

        assert job.correlation_id == correlation_id
        assert job.status == ProvisioningJobStatus.PENDING.value
        assert job.attempt_count == 0
        assert job.retry_count == 0
        assert len(job.history_entries) == 1
        assert job.history_entries[0].event_type == "job_created"


def test_job_completion_and_history_recording() -> None:
    correlation_id = unique_correlation_id("complete")

    with SessionLocal() as db:
        service = ProvisioningJobService(db)
        job = service.create_job(
            correlation_id=correlation_id,
            connector="github",
            operation="create_group",
            target_type="group",
            target_id="Developers",
            max_attempts=2,
        )
        service.start_job(job, attempt=1)
        service.complete_job(
            job,
            status=ConnectorStatus.SUCCESS.value,
            message="Group synchronized",
            attempt=1,
            duration_ms=12.5,
            retryable=False,
            details={"external_id": "group-1"},
        )
        db.commit()
        job_id = job.id

    response = client.get(
        "/provisioning/history",
        headers=auth_headers("alice@example.com"),
        params={"job_id": job_id, "sort_order": "ascending"},
    )

    assert response.status_code == 200
    events = response.json()
    assert [event["event_type"] for event in events] == [
        "job_created",
        "job_started",
        "connector_result",
        "job_completed",
    ]
    assert events[2]["details"] == {"external_id": "group-1"}


def test_job_failure() -> None:
    correlation_id = unique_correlation_id("failure")

    with SessionLocal() as db:
        service = ProvisioningJobService(db)
        job = service.create_job(
            correlation_id=correlation_id,
            connector="zendesk",
            operation="grant_entitlement",
            target_type="entitlement",
            target_id="1",
            max_attempts=1,
        )
        service.start_job(job, attempt=1)
        service.fail_job(
            job,
            status=ConnectorStatus.FAILED.value,
            message="Validation failed",
            attempt=1,
            duration_ms=3.0,
            retryable=False,
        )
        db.commit()
        job_id = job.id

    with SessionLocal() as db:
        job = ProvisioningJobService(db).lookup_job(job_id)

        assert job.status == ConnectorStatus.FAILED.value
        assert job.last_error == "Validation failed"
        assert job.completed_at is not None


def test_retry_recording() -> None:
    correlation_id = unique_correlation_id("retry")

    with SessionLocal() as db:
        service = ProvisioningJobService(db)
        job = service.create_job(
            correlation_id=correlation_id,
            connector="salesforce",
            operation="create_user",
            target_type="user",
            target_id="retry@example.com",
            max_attempts=2,
        )
        service.start_job(job, attempt=1)
        history = service.record_retry(
            job,
            attempt=1,
            next_attempt=2,
            delay_ms=100,
            reason="Rate limited",
        )
        db.commit()

        assert job.retry_count == 1
        assert job.retryable is True
        assert history.event_type == ProvisioningHistoryEventType.RETRY_RECORDED.value


def test_orchestrator_persists_job_history_and_correlation_id() -> None:
    clear_published_events()
    correlation_id = unique_correlation_id("orchestrator")
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
            correlation_id=correlation_id,
            db=db,
            requester_id=requester["id"],
            target_user_id=target["id"],
        )
        db.commit()

    jobs_response = client.get(
        "/provisioning/jobs",
        headers=auth_headers("alice@example.com"),
        params={"correlation_id": correlation_id},
    )
    history_response = client.get(
        "/provisioning/history",
        headers=auth_headers("alice@example.com"),
        params={"correlation_id": correlation_id},
    )

    assert result.status == ConnectorStatus.SUCCESS
    assert result.correlation_id == correlation_id
    assert jobs_response.status_code == 200
    assert len(jobs_response.json()) == 1
    job = jobs_response.json()[0]
    assert job["correlation_id"] == correlation_id
    assert job["status"] == ConnectorStatus.SUCCESS.value
    assert job["attempt_count"] == 1
    assert history_response.status_code == 200
    assert {
        entry["event_type"] for entry in history_response.json()
    } >= {"job_created", "job_started", "connector_invocation", "job_completed"}
    assert any(
        isinstance(event, ProvisioningJobCreated)
        for event in get_published_events()
    )
    assert any(
        isinstance(event, ProvisioningJobCompleted)
        for event in get_published_events()
    )


def test_orchestrator_persists_retry_tracking() -> None:
    clear_published_events()
    correlation_id = unique_correlation_id("retry-orchestrator")
    requester = find_user_by_email("alice@example.com")
    target = find_user_by_email("bob@example.com")
    registry = ConnectorRegistry([SalesforceConnector(failures_before_success=1)])
    orchestrator = ProvisioningOrchestrator(
        registry=registry,
        retry_policy=RetryPolicy(max_attempts=2),
    )

    with SessionLocal() as db:
        result = orchestrator.execute(
            connector_name="salesforce",
            operation=ConnectorOperation.CREATE_USER,
            payload={"email": "retry-orchestrator@example.com"},
            correlation_id=correlation_id,
            db=db,
            requester_id=requester["id"],
            target_user_id=target["id"],
        )
        db.commit()

    jobs_response = client.get(
        "/provisioning/jobs",
        headers=auth_headers("alice@example.com"),
        params={"correlation_id": correlation_id},
    )
    history_response = client.get(
        "/provisioning/history",
        headers=auth_headers("alice@example.com"),
        params={
            "correlation_id": correlation_id,
            "event_type": "retry_recorded",
        },
    )

    assert result.status == ConnectorStatus.SUCCESS
    assert jobs_response.json()[0]["retry_count"] == 1
    assert history_response.status_code == 200
    assert len(history_response.json()) == 1
    assert history_response.json()[0]["details"]["next_attempt"] == 2
    assert any(
        isinstance(event, ProvisioningRetryRecorded)
        for event in get_published_events()
    )


def test_orchestrator_persists_failed_job() -> None:
    clear_published_events()
    correlation_id = unique_correlation_id("failed-orchestrator")
    requester = find_user_by_email("alice@example.com")
    target = find_user_by_email("bob@example.com")
    registry = ConnectorRegistry(
        [
            SalesforceConnector(
                simulation_mode=ConnectorSimulationMode.NON_RETRYABLE_FAILURE
            )
        ]
    )
    orchestrator = ProvisioningOrchestrator(registry=registry)

    with SessionLocal() as db:
        result = orchestrator.execute(
            connector_name="salesforce",
            operation=ConnectorOperation.CREATE_USER,
            payload={"email": "failed-orchestrator@example.com"},
            correlation_id=correlation_id,
            db=db,
            requester_id=requester["id"],
            target_user_id=target["id"],
        )
        db.commit()

    jobs_response = client.get(
        "/provisioning/jobs",
        headers=auth_headers("alice@example.com"),
        params={"correlation_id": correlation_id},
    )

    assert result.status == ConnectorStatus.FAILED
    assert jobs_response.json()[0]["status"] == ConnectorStatus.FAILED.value
    assert jobs_response.json()[0]["last_error"] == "Simulated non-retryable failure"
    assert any(
        isinstance(event, ProvisioningJobFailed)
        for event in get_published_events()
    )


def test_list_jobs_and_lookup_job() -> None:
    correlation_id = unique_correlation_id("lookup")

    with SessionLocal() as db:
        service = ProvisioningJobService(db)
        job = service.create_job(
            correlation_id=correlation_id,
            connector="finance",
            operation="disable_user",
            target_type="user",
            target_id="123",
            max_attempts=1,
        )
        db.commit()
        job_id = job.id

    list_response = client.get(
        "/provisioning/jobs",
        headers=auth_headers("alice@example.com"),
        params={"connector": "finance", "correlation_id": correlation_id},
    )
    lookup_response = client.get(
        f"/provisioning/jobs/{job_id}",
        headers=auth_headers("alice@example.com"),
    )

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert lookup_response.status_code == 200
    assert lookup_response.json()["id"] == job_id


def test_history_endpoint_filtering_and_sorting() -> None:
    correlation_id = unique_correlation_id("history")

    with SessionLocal() as db:
        service = ProvisioningJobService(db)
        job = service.create_job(
            correlation_id=correlation_id,
            connector="github",
            operation="add_group_member",
            target_type="group",
            target_id="1",
            max_attempts=1,
        )
        service.start_job(job, attempt=1)
        db.commit()

    response = client.get(
        "/provisioning/history",
        headers=auth_headers("alice@example.com"),
        params={
            "correlation_id": correlation_id,
            "sort_order": "ascending",
            "count": 1,
        },
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["event_type"] == "job_created"


def test_provisioning_endpoints_require_authentication_and_rbac() -> None:
    unauthenticated_response = client.get("/provisioning/jobs")
    employee_response = client.get(
        "/provisioning/jobs",
        headers=auth_headers("bob@example.com"),
    )

    assert unauthenticated_response.status_code == 401
    assert employee_response.status_code == 403


def test_audit_integration_includes_correlation_id() -> None:
    correlation_id = unique_correlation_id("audit")
    requester = find_user_by_email("alice@example.com")
    target = find_user_by_email("bob@example.com")
    registry = ConnectorRegistry([SalesforceConnector(failures_before_success=1)])
    orchestrator = ProvisioningOrchestrator(
        registry=registry,
        retry_policy=RetryPolicy(max_attempts=2),
    )

    with SessionLocal() as db:
        orchestrator.execute(
            connector_name="salesforce",
            operation=ConnectorOperation.CREATE_USER,
            payload={"email": "audit-correlation@example.com"},
            correlation_id=correlation_id,
            db=db,
            requester_id=requester["id"],
            target_user_id=target["id"],
        )
        db.commit()

    completed_response = client.get(
        "/audit-events",
        headers=auth_headers("alice@example.com"),
        params={
            "action": ACTION_PROVISIONING_JOB_COMPLETED,
            "correlation_id": correlation_id,
        },
    )
    retry_response = client.get(
        "/audit-events",
        headers=auth_headers("alice@example.com"),
        params={
            "action": ACTION_PROVISIONING_RETRY_RECORDED,
            "correlation_id": correlation_id,
        },
    )

    assert completed_response.status_code == 200
    assert retry_response.status_code == 200
    assert completed_response.json()[0]["correlation_id"] == correlation_id
    assert retry_response.json()[0]["correlation_id"] == correlation_id


def test_failure_audit_integration() -> None:
    correlation_id = unique_correlation_id("failure-audit")
    requester = find_user_by_email("alice@example.com")
    target = find_user_by_email("bob@example.com")
    registry = ConnectorRegistry(
        [
            SalesforceConnector(
                simulation_mode=ConnectorSimulationMode.NON_RETRYABLE_FAILURE
            )
        ]
    )
    orchestrator = ProvisioningOrchestrator(registry=registry)

    with SessionLocal() as db:
        orchestrator.execute(
            connector_name="salesforce",
            operation=ConnectorOperation.CREATE_USER,
            payload={"email": "failure-audit@example.com"},
            correlation_id=correlation_id,
            db=db,
            requester_id=requester["id"],
            target_user_id=target["id"],
        )
        db.commit()

    response = client.get(
        "/audit-events",
        headers=auth_headers("alice@example.com"),
        params={
            "action": ACTION_PROVISIONING_JOB_FAILED,
            "correlation_id": correlation_id,
        },
    )

    assert response.status_code == 200
    assert response.json()[0]["result"] == "denied"


def test_provisioning_openapi_metadata() -> None:
    schema = client.get("/openapi.json").json()

    assert "/provisioning/jobs" in schema["paths"]
    assert "/provisioning/jobs/{job_id}" in schema["paths"]
    assert "/provisioning/history" in schema["paths"]


def test_unsupported_sort_returns_400() -> None:
    response = client.get(
        "/provisioning/jobs",
        headers=auth_headers("alice@example.com"),
        params={"sort_by": "not_supported"},
    )

    assert response.status_code == 400


def test_service_list_jobs_filtering() -> None:
    correlation_id = unique_correlation_id("service-list")

    with SessionLocal() as db:
        service = ProvisioningJobService(db)
        service.create_job(
            correlation_id=correlation_id,
            connector="salesforce",
            operation="delete_user",
            target_type="user",
            target_id="555",
            max_attempts=1,
        )
        db.commit()

    with SessionLocal() as db:
        jobs = ProvisioningJobService(db).list_jobs(
            filters=ProvisioningJobFilters(
                connector="salesforce",
                correlation_id=correlation_id,
            ),
            offset=0,
            limit=10,
        )

        assert len(jobs) == 1
        assert jobs[0].target_id == "555"
