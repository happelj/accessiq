from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.delegation.models import DelegationAssignment
from app.domain.events import (
    DelegatedAccessDenied,
    DelegatedAccessGranted,
    DelegationAssigned,
    DelegationRemoved,
)
from app.domain.publisher import clear_published_events, get_published_events
from app.main import app
from app.scim.constants import SCIM_SCHEMA_GROUP

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


def create_user(
    *,
    prefix: str = "delegation-user",
    department: str = "Engineering",
    active: bool = True,
    operator_role: str = "employee",
) -> dict[str, Any]:
    response = client.post(
        "/users",
        json={
            "name": "Delegation Test User",
            "email": f"{prefix}-{uuid4()}@example.com",
            "department": department,
            "active": active,
            "operator_role": operator_role,
        },
    )

    assert response.status_code == 201

    return response.json()


def create_group() -> dict[str, Any]:
    response = client.post(
        "/scim/v2/Groups",
        headers=auth_headers("alice@example.com"),
        json={
            "schemas": [SCIM_SCHEMA_GROUP],
            "displayName": f"Delegation Group {uuid4()}",
            "members": [],
        },
    )

    assert response.status_code == 201

    return response.json()


def assign_delegation(
    *,
    delegate_user_id: int,
    scope_type: str = "APPLICATION",
    scope_id: int | None = None,
    delegation_role: str = "HELPDESK_DELEGATE",
    expires_at: str | None = None,
    requester_email: str = "alice@example.com",
) -> Any:
    application = find_application_by_slug("salesforce")
    payload: dict[str, Any] = {
        "delegate_user_id": delegate_user_id,
        "scope_type": scope_type,
        "scope_id": scope_id or application["id"],
        "delegation_role": delegation_role,
    }
    if expires_at is not None:
        payload["expires_at"] = expires_at

    return client.post(
        "/delegation/assignments",
        headers=auth_headers(requester_email),
        json=payload,
    )


def grant_access(
    *,
    requester_email: str,
    target_user_id: int,
    entitlement_id: int,
) -> Any:
    return client.post(
        "/access/grant",
        headers=auth_headers(requester_email),
        json={
            "target_user_id": target_user_id,
            "entitlement_id": entitlement_id,
        },
    )


def revoke_access(
    *,
    requester_email: str,
    target_user_id: int,
    entitlement_id: int,
) -> Any:
    return client.post(
        "/access/revoke",
        headers=auth_headers(requester_email),
        json={
            "target_user_id": target_user_id,
            "entitlement_id": entitlement_id,
        },
    )


def get_audit_events(**params: Any) -> list[dict[str, Any]]:
    response = client.get(
        "/audit-events",
        headers=auth_headers("alice@example.com"),
        params=params,
    )

    assert response.status_code == 200

    return response.json()


def insert_expired_assignment(delegate_user_id: int, scope_id: int) -> int:
    actor = find_user_by_email("alice@example.com")
    with SessionLocal() as db:
        assignment = DelegationAssignment(
            delegate_user_id=delegate_user_id,
            scope_type="APPLICATION",
            scope_id=scope_id,
            delegation_role="HELPDESK_DELEGATE",
            created_by=actor["id"],
            expires_at=datetime.now(UTC) - timedelta(days=1),
            active=True,
        )
        db.add(assignment)
        db.commit()
        return assignment.id


def test_assign_delegation() -> None:
    delegate = create_user()
    response = assign_delegation(delegate_user_id=delegate["id"])

    assert response.status_code == 201
    body = response.json()
    assert body["delegate_user_id"] == delegate["id"]
    assert body["scope_type"] == "APPLICATION"
    assert body["delegation_role"] == "HELPDESK_DELEGATE"
    assert body["active"] is True


def test_remove_delegation() -> None:
    delegate = create_user()
    assignment = assign_delegation(delegate_user_id=delegate["id"]).json()

    response = client.delete(
        f"/delegation/assignments/{assignment['id']}",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 200
    assert response.json()["active"] is False


def test_duplicate_assignment() -> None:
    delegate = create_user()
    first = assign_delegation(delegate_user_id=delegate["id"])
    second = assign_delegation(delegate_user_id=delegate["id"])

    assert first.status_code == 201
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"]


def test_expired_assignment() -> None:
    delegate = create_user()
    target = create_user(prefix="delegation-target")
    application = find_application_by_slug("salesforce")
    entitlement = find_entitlement_by_slug("salesforce", "user")
    insert_expired_assignment(delegate["id"], application["id"])

    response = grant_access(
        requester_email=delegate["email"],
        target_user_id=target["id"],
        entitlement_id=entitlement["id"],
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient privileges"}


def test_inactive_assignment() -> None:
    delegate = create_user()
    target = create_user(prefix="delegation-target")
    entitlement = find_entitlement_by_slug("salesforce", "user")
    assignment = assign_delegation(delegate_user_id=delegate["id"]).json()
    client.delete(
        f"/delegation/assignments/{assignment['id']}",
        headers=auth_headers("alice@example.com"),
    )

    response = grant_access(
        requester_email=delegate["email"],
        target_user_id=target["id"],
        entitlement_id=entitlement["id"],
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient privileges"}


def test_lookup_assignment() -> None:
    delegate = create_user()
    assignment = assign_delegation(delegate_user_id=delegate["id"]).json()

    response = client.get(
        f"/delegation/assignments/{assignment['id']}",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 200
    assert response.json()["id"] == assignment["id"]


def test_list_assignments() -> None:
    delegate = create_user()
    assignment = assign_delegation(delegate_user_id=delegate["id"]).json()

    response = client.get(
        "/delegation/assignments",
        headers=auth_headers("alice@example.com"),
        params={"delegate_user_id": delegate["id"], "active": True},
    )

    assert response.status_code == 200
    assert any(item["id"] == assignment["id"] for item in response.json())


def test_scope_validation() -> None:
    delegate = create_user()
    group = create_group()
    group_assignment = assign_delegation(
        delegate_user_id=delegate["id"],
        scope_type="GROUP",
        scope_id=int(group["id"]),
        delegation_role="GROUP_OWNER",
    )
    invalid_role = assign_delegation(
        delegate_user_id=delegate["id"],
        scope_type="GROUP",
        scope_id=int(group["id"]),
        delegation_role="APPLICATION_OWNER",
    )
    unknown_scope = assign_delegation(
        delegate_user_id=delegate["id"],
        scope_type="APPLICATION",
        scope_id=999999,
        delegation_role="HELPDESK_DELEGATE",
    )

    assert group_assignment.status_code == 201
    assert invalid_role.status_code == 400
    assert unknown_scope.status_code == 404


def test_delegated_action_allowed() -> None:
    clear_published_events()
    delegate = create_user(prefix="delegated-operator")
    target = create_user(prefix="delegation-target")
    entitlement = find_entitlement_by_slug("salesforce", "user")
    assignment = assign_delegation(delegate_user_id=delegate["id"]).json()

    try:
        response = grant_access(
            requester_email=delegate["email"],
            target_user_id=target["id"],
            entitlement_id=entitlement["id"],
        )

        assert response.status_code == 201
        assert response.json()["user_id"] == target["id"]
        assert any(
            isinstance(event, DelegatedAccessGranted)
            and event.assignment_id == assignment["id"]
            for event in get_published_events()
        )
    finally:
        revoke_access(
            requester_email="alice@example.com",
            target_user_id=target["id"],
            entitlement_id=entitlement["id"],
        )


def test_delegated_action_denied() -> None:
    clear_published_events()
    delegate = create_user(prefix="delegated-operator")
    target = create_user(prefix="delegation-target")
    entitlement = find_entitlement_by_slug("salesforce", "user")

    response = grant_access(
        requester_email=delegate["email"],
        target_user_id=target["id"],
        entitlement_id=entitlement["id"],
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient privileges"}
    assert any(
        isinstance(event, DelegatedAccessDenied)
        for event in get_published_events()
    )


def test_authentication_and_rbac() -> None:
    delegate = create_user()
    application = find_application_by_slug("salesforce")
    unauthenticated = client.post(
        "/delegation/assignments",
        json={
            "delegate_user_id": delegate["id"],
            "scope_type": "APPLICATION",
            "scope_id": application["id"],
            "delegation_role": "HELPDESK_DELEGATE",
        },
    )
    auditor_response = assign_delegation(
        delegate_user_id=delegate["id"],
        requester_email="auditor@example.com",
    )

    assert unauthenticated.status_code == 401
    assert auditor_response.status_code == 403


def test_audit_events() -> None:
    delegate = create_user(prefix="delegated-operator")
    target = create_user(prefix="delegation-target")
    entitlement = find_entitlement_by_slug("salesforce", "user")
    assignment = assign_delegation(delegate_user_id=delegate["id"]).json()

    try:
        grant_response = grant_access(
            requester_email=delegate["email"],
            target_user_id=target["id"],
            entitlement_id=entitlement["id"],
        )
        assigned_events = get_audit_events(
            action="delegation_assigned",
            target_user_id=delegate["id"],
        )
        allowed_events = get_audit_events(
            action="delegated_action_allowed",
            requester_id=delegate["id"],
            target_user_id=target["id"],
        )

        assert grant_response.status_code == 201
        assert any(
            event["reason"] == f"Delegation assignment {assignment['id']} created"
            for event in assigned_events
        )
        assert any(
            event["reason"]
            == f"Delegation assignment {assignment['id']} permits this action"
            for event in allowed_events
        )
    finally:
        revoke_access(
            requester_email="alice@example.com",
            target_user_id=target["id"],
            entitlement_id=entitlement["id"],
        )


def test_domain_events() -> None:
    clear_published_events()
    delegate = create_user()
    assignment = assign_delegation(delegate_user_id=delegate["id"]).json()
    remove_response = client.delete(
        f"/delegation/assignments/{assignment['id']}",
        headers=auth_headers("alice@example.com"),
    )
    events = get_published_events()

    assert remove_response.status_code == 200
    assert any(isinstance(event, DelegationAssigned) for event in events)
    assert any(isinstance(event, DelegationRemoved) for event in events)


def test_pagination() -> None:
    first_delegate = create_user()
    second_delegate = create_user()
    group = create_group()
    first = assign_delegation(
        delegate_user_id=first_delegate["id"],
        scope_type="GROUP",
        scope_id=int(group["id"]),
        delegation_role="GROUP_OWNER",
    ).json()
    second = assign_delegation(
        delegate_user_id=second_delegate["id"],
        scope_type="GROUP",
        scope_id=int(group["id"]),
        delegation_role="GROUP_OWNER",
    ).json()

    response = client.get(
        "/delegation/assignments",
        headers=auth_headers("alice@example.com"),
        params={
            "scope_type": "GROUP",
            "scope_id": int(group["id"]),
            "start_index": 2,
            "count": 1,
            "sort_by": "id",
            "sort_order": "ascending",
        },
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == max(first["id"], second["id"])


def test_openapi_documents_delegation_endpoints() -> None:
    schema = client.get("/openapi.json").json()

    assert "/delegation/assignments" in schema["paths"]
    assert "/delegation/assignments/{assignment_id}" in schema["paths"]
