from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
import jwt

from app.config import get_auth_settings
from app.main import app


client = TestClient(app)


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

    raise AssertionError(f"Entitlement with slug {entitlement_slug!r} was not found")


def create_target_user(department: str = "Engineering") -> dict[str, Any]:
    unique_email = f"rbac-target-{uuid4()}@example.com"
    response = client.post(
        "/users",
        json={
            "name": "RBAC Target",
            "email": unique_email,
            "department": department,
            "active": True,
            "operator_role": "employee",
        },
    )

    assert response.status_code == 201

    return response.json()


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


def test_security_admin_can_grant() -> None:
    target_user = create_target_user()
    entitlement = find_entitlement_by_slug("salesforce", "user")

    try:
        response = grant_access(
            requester_email="alice@example.com",
            target_user_id=target_user["id"],
            entitlement_id=entitlement["id"],
        )

        assert response.status_code == 201
        assert response.json()["user_id"] == target_user["id"]
    finally:
        revoke_access(
            requester_email="alice@example.com",
            target_user_id=target_user["id"],
            entitlement_id=entitlement["id"],
        )


def test_iam_admin_can_grant() -> None:
    target_user = create_target_user()
    entitlement = find_entitlement_by_slug("salesforce", "user")

    try:
        response = grant_access(
            requester_email="ian@example.com",
            target_user_id=target_user["id"],
            entitlement_id=entitlement["id"],
        )

        assert response.status_code == 201
        assert response.json()["user_id"] == target_user["id"]
    finally:
        revoke_access(
            requester_email="alice@example.com",
            target_user_id=target_user["id"],
            entitlement_id=entitlement["id"],
        )


def test_helpdesk_cannot_grant() -> None:
    target_user = create_target_user()
    entitlement = find_entitlement_by_slug("salesforce", "user")

    response = grant_access(
        requester_email="sarah@example.com",
        target_user_id=target_user["id"],
        entitlement_id=entitlement["id"],
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient privileges"}


def test_employee_cannot_grant() -> None:
    target_user = create_target_user()
    entitlement = find_entitlement_by_slug("salesforce", "user")

    response = grant_access(
        requester_email="bob@example.com",
        target_user_id=target_user["id"],
        entitlement_id=entitlement["id"],
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient privileges"}


def test_auditor_cannot_grant() -> None:
    target_user = create_target_user()
    entitlement = find_entitlement_by_slug("salesforce", "user")

    response = grant_access(
        requester_email="auditor@example.com",
        target_user_id=target_user["id"],
        entitlement_id=entitlement["id"],
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient privileges"}


def test_security_admin_can_revoke() -> None:
    target_user = create_target_user()
    entitlement = find_entitlement_by_slug("salesforce", "user")
    grant_response = grant_access(
        requester_email="alice@example.com",
        target_user_id=target_user["id"],
        entitlement_id=entitlement["id"],
    )
    revoke_response = revoke_access(
        requester_email="alice@example.com",
        target_user_id=target_user["id"],
        entitlement_id=entitlement["id"],
    )

    assert grant_response.status_code == 201
    assert revoke_response.status_code == 200


def test_iam_admin_can_revoke() -> None:
    target_user = create_target_user()
    entitlement = find_entitlement_by_slug("salesforce", "user")
    grant_response = grant_access(
        requester_email="ian@example.com",
        target_user_id=target_user["id"],
        entitlement_id=entitlement["id"],
    )
    revoke_response = revoke_access(
        requester_email="ian@example.com",
        target_user_id=target_user["id"],
        entitlement_id=entitlement["id"],
    )

    assert grant_response.status_code == 201
    assert revoke_response.status_code == 200


def test_auditor_can_view_audit_events() -> None:
    response = client.get(
        "/audit-events",
        headers=auth_headers("auditor@example.com"),
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_employee_cannot_view_audit_events() -> None:
    response = client.get(
        "/audit-events",
        headers=auth_headers("bob@example.com"),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient privileges"}


def test_missing_jwt_returns_401() -> None:
    target_user = create_target_user()
    entitlement = find_entitlement_by_slug("salesforce", "user")

    response = client.post(
        "/access/grant",
        json={
            "target_user_id": target_user["id"],
            "entitlement_id": entitlement["id"],
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_invalid_jwt_returns_401() -> None:
    target_user = create_target_user()
    entitlement = find_entitlement_by_slug("salesforce", "user")

    response = client.post(
        "/access/grant",
        headers={"Authorization": "Bearer not-a-valid-token"},
        json={
            "target_user_id": target_user["id"],
            "entitlement_id": entitlement["id"],
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_expired_jwt_returns_401() -> None:
    target_user = create_target_user()
    entitlement = find_entitlement_by_slug("salesforce", "user")
    settings = get_auth_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(find_user_by_email("alice@example.com")["id"]),
            "iat": int((now - timedelta(minutes=10)).timestamp()),
            "exp": int((now - timedelta(minutes=5)).timestamp()),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    response = client.post(
        "/access/grant",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "target_user_id": target_user["id"],
            "entitlement_id": entitlement["id"],
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_authenticated_but_forbidden_returns_403() -> None:
    target_user = create_target_user()
    entitlement = find_entitlement_by_slug("salesforce", "user")

    response = grant_access(
        requester_email="manager@example.com",
        target_user_id=target_user["id"],
        entitlement_id=entitlement["id"],
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient privileges"}


def test_business_policy_engine_executes_after_rbac_passes() -> None:
    target_user = create_target_user(department="Engineering")
    entitlement = find_entitlement_by_slug("finance-portal", "read-only")

    response = grant_access(
        requester_email="alice@example.com",
        target_user_id=target_user["id"],
        entitlement_id=entitlement["id"],
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Finance Portal access is restricted to Finance employees"
    }


def test_audit_logging_behavior_is_unchanged_after_rbac() -> None:
    requester = find_user_by_email("alice@example.com")
    target_user = create_target_user()
    entitlement = find_entitlement_by_slug("salesforce", "user")

    try:
        grant_response = grant_access(
            requester_email=requester["email"],
            target_user_id=target_user["id"],
            entitlement_id=entitlement["id"],
        )
        audit_response = client.get(
            "/audit-events",
            headers=auth_headers("auditor@example.com"),
            params={
                "requester_id": requester["id"],
                "target_user_id": target_user["id"],
                "action": "grant",
                "result": "succeeded",
            },
        )

        assert grant_response.status_code == 201
        assert audit_response.status_code == 200
        assert any(
            event["requester_id"] == requester["id"]
            and event["target_user_id"] == target_user["id"]
            and event["entitlement_id"] == entitlement["id"]
            for event in audit_response.json()
        )
    finally:
        revoke_access(
            requester_email="alice@example.com",
            target_user_id=target_user["id"],
            entitlement_id=entitlement["id"],
        )
