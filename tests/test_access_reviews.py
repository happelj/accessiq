from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.domain.events import (
    CertificationCampaignCancelled,
    CertificationCampaignCompleted,
    CertificationCampaignCreated,
    CertificationCampaignStarted,
    CertificationDecisionRecorded,
    CertificationDecisionUpdated,
)
from app.domain.publisher import clear_published_events, get_published_events
from app.main import app
from app.models import AccessAssignment

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


def unique_name(prefix: str = "campaign") -> str:
    return f"{prefix}-{uuid4()}"


def create_target_user() -> dict[str, Any]:
    response = client.post(
        "/users",
        json={
            "name": "Access Review Target",
            "email": f"review-target-{uuid4()}@example.com",
            "department": "Engineering",
            "active": True,
            "operator_role": "employee",
        },
    )

    assert response.status_code == 201

    return response.json()


def create_campaign(
    *,
    name: str | None = None,
    reviewer_id: int | None = None,
    requester_email: str = "alice@example.com",
) -> dict[str, Any]:
    reviewer = reviewer_id or find_user_by_email("alice@example.com")["id"]
    response = client.post(
        "/access-reviews/campaigns",
        headers=auth_headers(requester_email),
        json={
            "name": name or unique_name("review"),
            "description": "Automated certification campaign test",
            "reviewer_id": reviewer,
        },
    )

    assert response.status_code == 201

    return response.json()


def grant_access_for_review() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
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


def count_access_assignments() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count(AccessAssignment.id))) or 0


def start_campaign(campaign_id: int) -> dict[str, Any]:
    response = client.post(
        f"/access-reviews/campaigns/{campaign_id}/start",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 200

    return response.json()


def get_campaign_items(campaign_id: int) -> list[dict[str, Any]]:
    response = client.get(
        f"/access-reviews/campaigns/{campaign_id}/items",
        headers=auth_headers("alice@example.com"),
        params={"count": 500},
    )

    assert response.status_code == 200

    return response.json()


def create_started_campaign_with_access(
    prefix: str = "active-review",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    target, entitlement, assignment = grant_access_for_review()
    campaign = create_campaign(name=unique_name(prefix))
    started = start_campaign(campaign["id"])
    items = get_campaign_items(campaign["id"])

    assert any(item["access_assignment_id"] == assignment["id"] for item in items)

    return target, entitlement, started, items


def record_decision(
    item_id: int,
    decision: str,
    comments: str | None = None,
    requester_email: str = "alice@example.com",
) -> dict[str, Any]:
    response = client.post(
        f"/access-reviews/items/{item_id}/decision",
        headers=auth_headers(requester_email),
        json={
            "decision": decision,
            "comments": comments,
        },
    )

    assert response.status_code == 200

    return response.json()


def record_decision_for_all_items(
    campaign_id: int,
    decision: str = "APPROVE",
) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for item in get_campaign_items(campaign_id):
        decisions.append(
            record_decision(
                item["id"],
                decision,
                comments=f"{decision.lower()} for test completion",
            )
        )

    return decisions


def test_campaign_creation() -> None:
    clear_published_events()
    campaign = create_campaign(name=unique_name("create"))

    assert campaign["status"] == "DRAFT"
    assert campaign["total_items"] == 0
    assert campaign["completed_items"] == 0
    assert campaign["completion_percentage"] == 0.0
    assert any(
        isinstance(event, CertificationCampaignCreated)
        for event in get_published_events()
    )

    audit_response = client.get(
        "/audit-events",
        headers=auth_headers("alice@example.com"),
        params={"action": "certification_campaign_created"},
    )

    assert audit_response.status_code == 200
    assert any(
        event["reason"] == f"Certification campaign {campaign['id']} created"
        for event in audit_response.json()
    )


def test_duplicate_campaign() -> None:
    name = unique_name("duplicate")
    create_campaign(name=name)

    response = client.post(
        "/access-reviews/campaigns",
        headers=auth_headers("alice@example.com"),
        json={
            "name": name,
            "description": "duplicate",
            "reviewer_id": find_user_by_email("alice@example.com")["id"],
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Certification campaign already exists"}


def test_list_campaigns() -> None:
    campaign = create_campaign(name=unique_name("list"))

    response = client.get(
        "/access-reviews/campaigns",
        headers=auth_headers("alice@example.com"),
        params={"status": "DRAFT", "count": 100},
    )

    assert response.status_code == 200
    assert any(item["id"] == campaign["id"] for item in response.json())


def test_lookup_campaign() -> None:
    campaign = create_campaign(name=unique_name("lookup"))

    response = client.get(
        f"/access-reviews/campaigns/{campaign['id']}",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 200
    assert response.json()["id"] == campaign["id"]


def test_start_campaign() -> None:
    clear_published_events()
    grant_access_for_review()
    expected_total = count_access_assignments()
    campaign = create_campaign(name=unique_name("start"))

    response = client.post(
        f"/access-reviews/campaigns/{campaign['id']}/start",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ACTIVE"
    assert body["total_items"] == expected_total
    assert body["started_at"] is not None
    assert any(
        isinstance(event, CertificationCampaignStarted)
        for event in get_published_events()
    )


def test_cancel_campaign() -> None:
    clear_published_events()
    campaign = create_campaign(name=unique_name("cancel"))

    response = client.post(
        f"/access-reviews/campaigns/{campaign['id']}/cancel",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert response.json()["cancelled_at"] is not None
    assert any(
        isinstance(event, CertificationCampaignCancelled)
        for event in get_published_events()
    )


def test_complete_campaign() -> None:
    clear_published_events()
    _, _, campaign, _ = create_started_campaign_with_access("complete")
    record_decision_for_all_items(campaign["id"], "APPROVE")

    response = client.post(
        f"/access-reviews/campaigns/{campaign['id']}/complete",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"
    assert response.json()["completed_at"] is not None
    assert any(
        isinstance(event, CertificationCampaignCompleted)
        for event in get_published_events()
    )


def test_invalid_state_transition() -> None:
    campaign = create_campaign(name=unique_name("transition"))
    start_campaign(campaign["id"])

    response = client.post(
        f"/access-reviews/campaigns/{campaign['id']}/start",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 409
    assert "Cannot transition campaign from ACTIVE to ACTIVE" in response.json()[
        "detail"
    ]


def test_review_generation() -> None:
    target, entitlement, assignment = grant_access_for_review()
    campaign = create_campaign(name=unique_name("generation"))
    start_campaign(campaign["id"])

    items = get_campaign_items(campaign["id"])
    generated_item = next(
        item for item in items if item["access_assignment_id"] == assignment["id"]
    )

    assert generated_item["user_id"] == target["id"]
    assert generated_item["application"] == "Salesforce"
    assert generated_item["entitlement_id"] == entitlement["id"]
    assert generated_item["status"] == "PENDING"


def test_review_lookup() -> None:
    _, _, campaign, items = create_started_campaign_with_access("item-lookup")
    item = items[0]

    response = client.get(
        f"/access-reviews/items/{item['id']}",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 200
    assert response.json()["id"] == item["id"]
    assert response.json()["campaign_id"] == campaign["id"]


def test_approve_decision() -> None:
    clear_published_events()
    _, _, campaign, items = create_started_campaign_with_access("approve")

    response = record_decision(
        items[0]["id"],
        "APPROVE",
        comments="Access remains appropriate",
    )
    summary = client.get(
        f"/access-reviews/campaigns/{campaign['id']}/summary",
        headers=auth_headers("alice@example.com"),
    ).json()

    assert response["decision"] == "APPROVE"
    assert response["comments"] == "Access remains appropriate"
    assert summary["approval_count"] >= 1
    assert any(
        isinstance(event, CertificationDecisionRecorded)
        for event in get_published_events()
    )


def test_revoke_decision_does_not_remove_access() -> None:
    target, entitlement, _, items = create_started_campaign_with_access("revoke")
    target_item = next(item for item in items if item["user_id"] == target["id"])

    response = record_decision(
        target_item["id"],
        "REVOKE",
        comments="Access should be removed later",
    )
    access_response = client.get(f"/users/{target['id']}/access")

    assert response["decision"] == "REVOKE"
    assert access_response.status_code == 200
    assert any(
        assignment["entitlement_id"] == entitlement["id"]
        for assignment in access_response.json()
    )


def test_abstain_decision() -> None:
    _, _, campaign, items = create_started_campaign_with_access("abstain")

    response = record_decision(
        items[0]["id"],
        "ABSTAIN",
        comments="Reviewer needs more context",
    )
    summary_response = client.get(
        f"/access-reviews/campaigns/{campaign['id']}/summary",
        headers=auth_headers("alice@example.com"),
    )

    assert response["decision"] == "ABSTAIN"
    assert summary_response.status_code == 200
    assert summary_response.json()["abstain_count"] >= 1


def test_update_decision() -> None:
    clear_published_events()
    _, _, campaign, items = create_started_campaign_with_access("update")
    record_decision(items[0]["id"], "APPROVE")

    response = record_decision(
        items[0]["id"],
        "REVOKE",
        comments="Correction after review",
    )
    summary = client.get(
        f"/access-reviews/campaigns/{campaign['id']}/summary",
        headers=auth_headers("alice@example.com"),
    ).json()

    assert response["decision"] == "REVOKE"
    assert response["comments"] == "Correction after review"
    assert summary["revocation_count"] >= 1
    assert any(
        isinstance(event, CertificationDecisionUpdated)
        for event in get_published_events()
    )


def test_completed_campaign_rejects_new_decisions() -> None:
    _, _, campaign, items = create_started_campaign_with_access("reject-complete")
    record_decision_for_all_items(campaign["id"], "APPROVE")
    complete_response = client.post(
        f"/access-reviews/campaigns/{campaign['id']}/complete",
        headers=auth_headers("alice@example.com"),
    )

    response = client.post(
        f"/access-reviews/items/{items[0]['id']}/decision",
        headers=auth_headers("alice@example.com"),
        json={
            "decision": "ABSTAIN",
            "comments": "too late",
        },
    )

    assert complete_response.status_code == 200
    assert response.status_code == 409
    assert response.json() == {
        "detail": "Decisions can only be recorded for active campaigns"
    }


def test_campaign_summary_and_completion_percentage() -> None:
    _, _, campaign, items = create_started_campaign_with_access("summary")
    record_decision(items[0]["id"], "APPROVE")

    response = client.get(
        f"/access-reviews/campaigns/{campaign['id']}/summary",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 200
    summary = response.json()
    assert summary["total_items"] == campaign["total_items"]
    assert summary["completed_items"] == 1
    assert summary["pending_items"] == campaign["total_items"] - 1
    assert summary["completion_percentage"] > 0


def test_decision_counts() -> None:
    grant_access_for_review()
    grant_access_for_review()
    _, _, campaign, items = create_started_campaign_with_access("counts")
    record_decision(items[0]["id"], "APPROVE")
    record_decision(items[1]["id"], "REVOKE")
    record_decision(items[2]["id"], "ABSTAIN")

    summary = client.get(
        f"/access-reviews/campaigns/{campaign['id']}/summary",
        headers=auth_headers("alice@example.com"),
    ).json()

    assert summary["approval_count"] == 1
    assert summary["revocation_count"] == 1
    assert summary["abstain_count"] == 1


def test_authentication_and_rbac() -> None:
    alice = find_user_by_email("alice@example.com")
    unauthenticated_response = client.get("/access-reviews/campaigns")
    employee_response = client.get(
        "/access-reviews/campaigns",
        headers=auth_headers("bob@example.com"),
    )
    auditor_create_response = client.post(
        "/access-reviews/campaigns",
        headers=auth_headers("auditor@example.com"),
        json={
            "name": unique_name("auditor-create"),
            "reviewer_id": alice["id"],
        },
    )

    assert unauthenticated_response.status_code == 401
    assert employee_response.status_code == 403
    assert auditor_create_response.status_code == 403


def test_audit_events_for_decisions() -> None:
    target, _, _, items = create_started_campaign_with_access("audit")
    target_item = next(item for item in items if item["user_id"] == target["id"])

    record_decision(target_item["id"], "APPROVE")
    response = client.get(
        "/audit-events",
        headers=auth_headers("alice@example.com"),
        params={
            "action": "certification_review_approved",
            "target_user_id": target["id"],
        },
    )

    assert response.status_code == 200
    assert any(
        event["reason"] == f"Review item {target_item['id']} recorded as APPROVE"
        for event in response.json()
    )


def test_domain_events() -> None:
    clear_published_events()
    _, _, campaign, items = create_started_campaign_with_access("events")
    record_decision(items[0]["id"], "APPROVE")
    record_decision_for_all_items(campaign["id"], "APPROVE")
    client.post(
        f"/access-reviews/campaigns/{campaign['id']}/complete",
        headers=auth_headers("alice@example.com"),
    )

    events = get_published_events()
    assert any(isinstance(event, CertificationCampaignStarted) for event in events)
    assert any(isinstance(event, CertificationDecisionRecorded) for event in events)
    assert any(isinstance(event, CertificationCampaignCompleted) for event in events)


def test_pagination() -> None:
    grant_access_for_review()
    grant_access_for_review()
    campaign = create_campaign(name=unique_name("pagination"))
    start_campaign(campaign["id"])

    response = client.get(
        f"/access-reviews/campaigns/{campaign['id']}/items",
        headers=auth_headers("alice@example.com"),
        params={"start_index": 2, "count": 1},
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_missing_reviewer() -> None:
    response = client.post(
        "/access-reviews/campaigns",
        headers=auth_headers("alice@example.com"),
        json={
            "name": unique_name("missing-reviewer"),
            "reviewer_id": 999999,
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Reviewer not found"}


def test_unknown_campaign_and_review_item() -> None:
    campaign_response = client.get(
        "/access-reviews/campaigns/999999",
        headers=auth_headers("alice@example.com"),
    )
    item_response = client.get(
        "/access-reviews/items/999999",
        headers=auth_headers("alice@example.com"),
    )

    assert campaign_response.status_code == 404
    assert item_response.status_code == 404


def test_invalid_decision() -> None:
    _, _, _, items = create_started_campaign_with_access("invalid-decision")

    response = client.post(
        f"/access-reviews/items/{items[0]['id']}/decision",
        headers=auth_headers("alice@example.com"),
        json={
            "decision": "MAYBE",
            "comments": "invalid",
        },
    )

    assert response.status_code == 422


def test_openapi_documents_access_review_endpoints() -> None:
    schema = client.get("/openapi.json").json()

    assert "/access-reviews/campaigns" in schema["paths"]
    assert "/access-reviews/campaigns/{campaign_id}/start" in schema["paths"]
    assert "/access-reviews/campaigns/{campaign_id}/summary" in schema["paths"]
    assert "/access-reviews/items/{item_id}/decision" in schema["paths"]
