from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from jose import jwt

from app.config import get_auth_settings
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


def revoke_test_assignment(user_id: int, entitlement_id: int) -> None:
    response = client.post(
        "/access/revoke",
        headers=auth_headers("alice@example.com"),
        json={
            "target_user_id": user_id,
            "entitlement_id": entitlement_id,
        },
    )

    assert response.status_code in {200, 404}


def test_grant_succeeds_with_valid_admin_jwt() -> None:
    target_user = find_user_by_email("bob@example.com")
    entitlement = find_entitlement_by_slug("salesforce", "user")
    payload = {
        "target_user_id": target_user["id"],
        "entitlement_id": entitlement["id"],
    }

    revoke_test_assignment(payload["target_user_id"], payload["entitlement_id"])

    try:
        response = client.post(
            "/access/grant",
            headers=auth_headers("alice@example.com"),
            json=payload,
        )

        assert response.status_code == 201
        assert response.json()["user_id"] == target_user["id"]
    finally:
        revoke_test_assignment(payload["target_user_id"], payload["entitlement_id"])


def test_revoke_succeeds_with_valid_admin_jwt() -> None:
    target_user = find_user_by_email("bob@example.com")
    entitlement = find_entitlement_by_slug("salesforce", "user")
    payload = {
        "target_user_id": target_user["id"],
        "entitlement_id": entitlement["id"],
    }

    revoke_test_assignment(payload["target_user_id"], payload["entitlement_id"])

    grant_response = client.post(
        "/access/grant",
        headers=auth_headers("alice@example.com"),
        json=payload,
    )
    revoke_response = client.post(
        "/access/revoke",
        headers=auth_headers("alice@example.com"),
        json=payload,
    )

    assert grant_response.status_code == 201
    assert revoke_response.status_code == 200


def test_missing_bearer_token_returns_401() -> None:
    target_user = find_user_by_email("bob@example.com")
    entitlement = find_entitlement_by_slug("salesforce", "user")

    response = client.post(
        "/access/grant",
        json={
            "target_user_id": target_user["id"],
            "entitlement_id": entitlement["id"],
        },
    )

    assert response.status_code == 401


def test_malformed_bearer_token_returns_401() -> None:
    target_user = find_user_by_email("bob@example.com")
    entitlement = find_entitlement_by_slug("salesforce", "user")

    response = client.post(
        "/access/grant",
        headers={"Authorization": "Token not-a-bearer-token"},
        json={
            "target_user_id": target_user["id"],
            "entitlement_id": entitlement["id"],
        },
    )

    assert response.status_code == 401


def test_invalid_jwt_returns_401() -> None:
    target_user = find_user_by_email("bob@example.com")
    entitlement = find_entitlement_by_slug("salesforce", "user")

    response = client.post(
        "/access/grant",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
        json={
            "target_user_id": target_user["id"],
            "entitlement_id": entitlement["id"],
        },
    )

    assert response.status_code == 401


def test_expired_jwt_returns_401() -> None:
    target_user = find_user_by_email("bob@example.com")
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


def test_unknown_jwt_subject_returns_401() -> None:
    target_user = find_user_by_email("bob@example.com")
    entitlement = find_entitlement_by_slug("salesforce", "user")
    settings = get_auth_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "999999",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
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


def test_policy_denial_still_returns_expected_response() -> None:
    requester = find_user_by_email("sarah@example.com")
    target_user = find_user_by_email("bob@example.com")
    entitlement = find_entitlement_by_slug("salesforce", "administrator")

    response = client.post(
        "/access/grant",
        headers=auth_headers(requester["email"]),
        json={
            "target_user_id": target_user["id"],
            "entitlement_id": entitlement["id"],
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Requester lacks permission to grant administrator access"
    }


def test_duplicate_grant_still_behaves_correctly() -> None:
    target_user = find_user_by_email("bob@example.com")
    entitlement = find_entitlement_by_slug("salesforce", "user")
    payload = {
        "target_user_id": target_user["id"],
        "entitlement_id": entitlement["id"],
    }

    revoke_test_assignment(payload["target_user_id"], payload["entitlement_id"])

    try:
        first_response = client.post(
            "/access/grant",
            headers=auth_headers("alice@example.com"),
            json=payload,
        )
        second_response = client.post(
            "/access/grant",
            headers=auth_headers("alice@example.com"),
            json=payload,
        )

        assert first_response.status_code == 201
        assert second_response.status_code == 409
        assert second_response.json() == {
            "detail": "User already has this access"
        }
    finally:
        revoke_test_assignment(payload["target_user_id"], payload["entitlement_id"])


def test_audit_events_record_authenticated_requester() -> None:
    requester = find_user_by_email("alice@example.com")
    target_user = find_user_by_email("bob@example.com")
    entitlement = find_entitlement_by_slug("salesforce", "user")
    payload = {
        "target_user_id": target_user["id"],
        "entitlement_id": entitlement["id"],
    }

    revoke_test_assignment(payload["target_user_id"], payload["entitlement_id"])

    try:
        grant_response = client.post(
            "/access/grant",
            headers=auth_headers(requester["email"]),
            json=payload,
        )
        audit_response = client.get(
            "/audit-events",
            headers=auth_headers(requester["email"]),
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
        revoke_test_assignment(payload["target_user_id"], payload["entitlement_id"])


def test_requester_id_can_no_longer_be_spoofed() -> None:
    target_user = find_user_by_email("bob@example.com")
    entitlement = find_entitlement_by_slug("salesforce", "user")

    response = client.post(
        "/access/grant",
        headers=auth_headers("alice@example.com"),
        json={
            "requester_id": find_user_by_email("sarah@example.com")["id"],
            "target_user_id": target_user["id"],
            "entitlement_id": entitlement["id"],
        },
    )

    assert response.status_code == 422


def test_audit_endpoint_requires_authentication() -> None:
    response = client.get("/audit-events")

    assert response.status_code == 401
