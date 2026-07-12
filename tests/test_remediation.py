from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.domain.events import (
    RemediationCompleted,
    RemediationCreated,
    RemediationStarted,
)
from app.domain.publisher import clear_published_events, get_published_events
from app.governance.models import (
    CertificationCampaign,
    CertificationDecision,
    CertificationReviewItem,
)
from app.main import app
from app.models import ProvisioningHistory
from app.remediation.enums import RemediationStatus
from app.remediation.models import RemediationJob

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


def find_application_by_slug(slug: str) -> dict[str, Any]:
    response = client.get("/applications")
    assert response.status_code == 200

    for application in response.json():
        if application["slug"] == slug:
            return application

    raise AssertionError(f"Application with slug {slug!r} was not found")


def find_entitlement_by_slug(
    application_slug: str,
    entitlement_slug: str,
) -> dict[str, Any]:
    application = find_application_by_slug(application_slug)
    response = client.get(f"/applications/{application['id']}/entitlements")
    assert response.status_code == 200

    for entitlement in response.json():
        if entitlement["slug"] == entitlement_slug:
            return entitlement

    raise AssertionError(
        f"Entitlement with slug {entitlement_slug!r} was not found"
    )


def create_target_user() -> dict[str, Any]:
    response = client.post(
        "/users",
        json={
            "name": "Remediation Target",
            "email": f"remediation-target-{uuid4()}@example.com",
            "department": "Engineering",
            "active": True,
            "operator_role": "employee",
        },
    )

    assert response.status_code == 201

    return response.json()


def grant_salesforce_access() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    target = create_target_user()
    entitlement = find_entitlement_by_slug("salesforce", "user")
    response = client.post(
        "/access/grant",
        headers=auth_headers("alice@example.com"),
        json={
            "target_user_id": target["id"],
            "entitlement_id": entitlement["id"],
        },
    )

    assert response.status_code == 201

    return target, entitlement, response.json()


def create_certification_campaign(
    *,
    decision: str = "REVOKE",
    status: str = "COMPLETED",
) -> tuple[int, int, int]:
    target, entitlement, assignment = grant_salesforce_access()
    actor = find_user_by_email("alice@example.com")
    now = datetime.now(UTC)

    with SessionLocal() as db:
        campaign = CertificationCampaign(
            name=f"Remediation Campaign {uuid4()}",
            description="Remediation test campaign",
            status=status,
            created_by=actor["id"],
            default_reviewer_id=actor["id"],
            created_at=now,
            started_at=now,
            completed_at=now if status == "COMPLETED" else None,
            total_items=1,
            completed_items=1,
            approval_count=1 if decision == "APPROVE" else 0,
            revocation_count=1 if decision == "REVOKE" else 0,
            abstain_count=1 if decision == "ABSTAIN" else 0,
        )
        db.add(campaign)
        db.flush()
        item = CertificationReviewItem(
            campaign_id=campaign.id,
            access_assignment_id=assignment["id"],
            user_id=target["id"],
            application_id=entitlement["application_id"],
            entitlement_id=entitlement["id"],
            reviewer_id=actor["id"],
            status="COMPLETED",
            reviewed_at=now,
            created_at=now,
        )
        db.add(item)
        db.flush()
        db.add(
            CertificationDecision(
                campaign_id=campaign.id,
                review_item_id=item.id,
                reviewer_id=actor["id"],
                decision=decision,
                comments=f"{decision} for remediation test",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

        return campaign.id, item.id, target["id"]


def remediate_campaign(campaign_id: int) -> dict[str, Any]:
    response = client.post(
        f"/access-reviews/campaigns/{campaign_id}/remediate",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 200

    return response.json()


def test_remediation_job_creation() -> None:
    campaign_id, item_id, _ = create_certification_campaign()

    body = remediate_campaign(campaign_id)

    assert body["campaign_id"] == campaign_id
    assert body["created_jobs"] == 1
    assert body["jobs"][0]["review_item_id"] == item_id
    assert body["jobs"][0]["remediation_type"] == "REVOKE_ENTITLEMENT"


def test_remediation_execution() -> None:
    campaign_id, _, _ = create_certification_campaign()

    body = remediate_campaign(campaign_id)
    job = body["jobs"][0]

    assert job["status"] == "COMPLETED"
    assert job["started_at"] is not None
    assert job["completed_at"] is not None


def test_duplicate_prevention() -> None:
    campaign_id, _, _ = create_certification_campaign()
    first = remediate_campaign(campaign_id)
    second = remediate_campaign(campaign_id)

    assert first["created_jobs"] == 1
    assert second["created_jobs"] == 0
    assert second["jobs"][0]["id"] == first["jobs"][0]["id"]


def test_completed_campaign_remediation() -> None:
    campaign_id, _, _ = create_certification_campaign(status="COMPLETED")

    response = client.post(
        f"/access-reviews/campaigns/{campaign_id}/remediate",
        headers=auth_headers("ian@example.com"),
    )

    assert response.status_code == 200
    assert response.json()["jobs"][0]["status"] == "COMPLETED"


def test_active_campaign_rejected() -> None:
    campaign_id, _, _ = create_certification_campaign(status="ACTIVE")

    response = client.post(
        f"/access-reviews/campaigns/{campaign_id}/remediate",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 409
    assert "must be COMPLETED" in response.json()["detail"]


def test_provisioning_orchestration_invoked() -> None:
    campaign_id, _, _ = create_certification_campaign()

    body = remediate_campaign(campaign_id)
    job = body["jobs"][0]

    provisioning_response = client.get(
        "/provisioning/jobs",
        headers=auth_headers("alice@example.com"),
        params={"correlation_id": job["correlation_id"]},
    )

    assert provisioning_response.status_code == 200
    assert len(provisioning_response.json()) == 1
    assert provisioning_response.json()[0]["operation"] == "revoke_entitlement"


def test_provisioning_job_linkage() -> None:
    campaign_id, _, _ = create_certification_campaign()

    body = remediate_campaign(campaign_id)
    job = body["jobs"][0]
    lookup_response = client.get(
        f"/remediation/jobs/{job['id']}",
        headers=auth_headers("alice@example.com"),
    )

    assert lookup_response.status_code == 200
    assert lookup_response.json()["provisioning_job_id"] is not None


def test_provisioning_history_linkage() -> None:
    campaign_id, _, _ = create_certification_campaign()

    body = remediate_campaign(campaign_id)
    job = body["jobs"][0]
    history_response = client.get(
        "/provisioning/history",
        headers=auth_headers("alice@example.com"),
        params={"job_id": job["provisioning_job_id"]},
    )

    assert history_response.status_code == 200
    assert {
        history["event_type"] for history in history_response.json()
    } >= {"job_created", "connector_invocation", "job_completed"}


def test_audit_events() -> None:
    campaign_id, _, target_user_id = create_certification_campaign()

    body = remediate_campaign(campaign_id)
    audit_response = client.get(
        "/audit-events",
        headers=auth_headers("alice@example.com"),
        params={
            "action": "remediation_completed",
            "target_user_id": target_user_id,
            "correlation_id": body["jobs"][0]["correlation_id"],
        },
    )

    assert audit_response.status_code == 200
    assert len(audit_response.json()) == 1


def test_domain_events() -> None:
    clear_published_events()
    campaign_id, _, _ = create_certification_campaign()

    remediate_campaign(campaign_id)
    events = get_published_events()

    assert any(isinstance(event, RemediationCreated) for event in events)
    assert any(isinstance(event, RemediationStarted) for event in events)
    assert any(isinstance(event, RemediationCompleted) for event in events)


def test_list_remediation_jobs() -> None:
    campaign_id, _, _ = create_certification_campaign()
    body = remediate_campaign(campaign_id)

    response = client.get(
        "/remediation/jobs",
        headers=auth_headers("alice@example.com"),
        params={"campaign_id": campaign_id},
    )

    assert response.status_code == 200
    assert any(job["id"] == body["jobs"][0]["id"] for job in response.json())


def test_lookup_remediation_job() -> None:
    campaign_id, _, _ = create_certification_campaign()
    body = remediate_campaign(campaign_id)

    response = client.get(
        f"/remediation/jobs/{body['jobs'][0]['id']}",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 200
    assert response.json()["id"] == body["jobs"][0]["id"]


def test_authentication_and_rbac() -> None:
    campaign_id, _, _ = create_certification_campaign()

    unauthenticated_response = client.post(
        f"/access-reviews/campaigns/{campaign_id}/remediate"
    )
    auditor_response = client.post(
        f"/access-reviews/campaigns/{campaign_id}/remediate",
        headers=auth_headers("auditor@example.com"),
    )

    assert unauthenticated_response.status_code == 401
    assert auditor_response.status_code == 403


def test_pagination() -> None:
    first_campaign_id, _, _ = create_certification_campaign()
    second_campaign_id, _, _ = create_certification_campaign()
    remediate_campaign(first_campaign_id)
    remediate_campaign(second_campaign_id)

    response = client.get(
        "/remediation/jobs",
        headers=auth_headers("alice@example.com"),
        params={"start_index": 2, "count": 1},
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_non_revoke_decisions_are_skipped() -> None:
    campaign_id, _, _ = create_certification_campaign(decision="APPROVE")

    body = remediate_campaign(campaign_id)

    assert body["created_jobs"] == 0
    assert body["executed_jobs"] == 0
    assert body["skipped_decisions"] == 1
    assert body["jobs"] == []


def test_unknown_campaign_and_job() -> None:
    campaign_response = client.post(
        "/access-reviews/campaigns/999999/remediate",
        headers=auth_headers("alice@example.com"),
    )
    job_response = client.get(
        "/remediation/jobs/999999",
        headers=auth_headers("alice@example.com"),
    )

    assert campaign_response.status_code == 404
    assert job_response.status_code == 404


def test_openapi_documents_remediation_endpoints() -> None:
    schema = client.get("/openapi.json").json()

    assert "/access-reviews/campaigns/{campaign_id}/remediate" in schema["paths"]
    assert "/remediation/jobs" in schema["paths"]
    assert "/remediation/jobs/{job_id}" in schema["paths"]


def test_remediation_jobs_persist_normalized_records() -> None:
    campaign_id, item_id, _ = create_certification_campaign()
    body = remediate_campaign(campaign_id)

    with SessionLocal() as db:
        count = db.scalar(
            select(func.count(RemediationJob.id)).where(
                RemediationJob.review_item_id == item_id
            )
        )
        history_count = db.scalar(
            select(func.count(ProvisioningHistory.id)).where(
                ProvisioningHistory.job_id == body["jobs"][0]["provisioning_job_id"]
            )
        )

    assert count == 1
    assert history_count and history_count > 0
