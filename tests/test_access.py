from typing import Any

from fastapi.testclient import TestClient

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


def find_application_by_slug(slug: str) -> dict[str, Any]:
    response = client.get("/applications")

    assert response.status_code == 200

    for application in response.json():
        if application["slug"] == slug:
            return application

    raise AssertionError(f"Application with slug {slug!r} was not found")


def find_entitlement_by_slug(
    application_id: int,
    slug: str,
) -> dict[str, Any]:
    response = client.get(f"/applications/{application_id}/entitlements")

    assert response.status_code == 200

    for entitlement in response.json():
        if entitlement["slug"] == slug:
            return entitlement

    raise AssertionError(f"Entitlement with slug {slug!r} was not found")


def find_user_by_email(email: str) -> dict[str, Any]:
    response = client.get("/users")

    assert response.status_code == 200

    for user in response.json():
        if user["email"] == email:
            return user

    raise AssertionError(f"User with email {email!r} was not found")


def get_employee_target() -> dict[str, Any]:
    return find_user_by_email("bob@example.com")


def revoke_test_assignment(
    user_id: int,
    entitlement_id: int,
) -> None:
    response = client.post(
        "/access/revoke",
        headers=auth_headers("alice@example.com"),
        json={
            "target_user_id": user_id,
            "entitlement_id": entitlement_id,
        },
    )

    assert response.status_code in {200, 404}


def get_salesforce_user_entitlement() -> dict[str, Any]:
    application = find_application_by_slug("salesforce")
    return find_entitlement_by_slug(application["id"], "user")


def test_list_applications_returns_seeded_applications() -> None:
    response = client.get("/applications")

    assert response.status_code == 200

    applications = response.json()
    slugs = {application["slug"] for application in applications}

    assert {
        "salesforce",
        "zendesk",
        "finance-portal",
        "github",
    }.issubset(slugs)


def test_salesforce_entitlements_are_returned() -> None:
    application = find_application_by_slug("salesforce")

    response = client.get(f"/applications/{application['id']}/entitlements")

    assert response.status_code == 200

    entitlements = response.json()
    slugs = {entitlement["slug"] for entitlement in entitlements}

    assert {"user", "administrator"}.issubset(slugs)


def test_missing_application_returns_404() -> None:
    response = client.get("/applications/999999/entitlements")

    assert response.status_code == 404
    assert response.json() == {"detail": "Application not found"}


def test_access_can_be_granted() -> None:
    target_user = get_employee_target()
    entitlement = get_salesforce_user_entitlement()
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

        body = response.json()

        assert body["user_id"] == payload["target_user_id"]
        assert body["application_id"] == entitlement["application_id"]
        assert body["application"] == "Salesforce"
        assert body["entitlement_id"] == entitlement["id"]
        assert body["entitlement"] == "Salesforce User"
        assert body["status"] == "active"
        assert "granted_at" in body
    finally:
        revoke_test_assignment(payload["target_user_id"], payload["entitlement_id"])


def test_duplicate_access_returns_409() -> None:
    target_user = get_employee_target()
    entitlement = get_salesforce_user_entitlement()
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
        assert second_response.json() == {"detail": "User already has this access"}
    finally:
        revoke_test_assignment(payload["target_user_id"], payload["entitlement_id"])


def test_granted_access_appears_in_user_access() -> None:
    target_user = get_employee_target()
    entitlement = get_salesforce_user_entitlement()
    payload = {
        "target_user_id": target_user["id"],
        "entitlement_id": entitlement["id"],
    }

    revoke_test_assignment(payload["target_user_id"], payload["entitlement_id"])

    try:
        grant_response = client.post(
            "/access/grant",
            headers=auth_headers("alice@example.com"),
            json=payload,
        )
        access_response = client.get(f"/users/{payload['target_user_id']}/access")

        assert grant_response.status_code == 201
        assert access_response.status_code == 200

        assignments = access_response.json()

        assert any(
            assignment["user_id"] == payload["target_user_id"]
            and assignment["entitlement_id"] == payload["entitlement_id"]
            and assignment["application"] == "Salesforce"
            and assignment["entitlement"] == "Salesforce User"
            and assignment["status"] == "active"
            for assignment in assignments
        )
    finally:
        revoke_test_assignment(payload["target_user_id"], payload["entitlement_id"])


def test_access_can_be_revoked() -> None:
    target_user = get_employee_target()
    entitlement = get_salesforce_user_entitlement()
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
    assert revoke_response.json() == {
        "status": "revoked",
        "user_id": payload["target_user_id"],
        "entitlement_id": payload["entitlement_id"],
    }


def test_revoking_missing_access_returns_404() -> None:
    target_user = get_employee_target()
    entitlement = get_salesforce_user_entitlement()
    payload = {
        "target_user_id": target_user["id"],
        "entitlement_id": entitlement["id"],
    }

    revoke_test_assignment(payload["target_user_id"], payload["entitlement_id"])

    response = client.post(
        "/access/revoke",
        headers=auth_headers("alice@example.com"),
        json=payload,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Access assignment not found"}


def test_missing_user_returns_404_when_granting() -> None:
    entitlement = get_salesforce_user_entitlement()

    response = client.post(
        "/access/grant",
        headers=auth_headers("alice@example.com"),
        json={
            "target_user_id": 999999,
            "entitlement_id": entitlement["id"],
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


def test_missing_entitlement_returns_404_when_granting() -> None:
    target_user = get_employee_target()

    response = client.post(
        "/access/grant",
        headers=auth_headers("alice@example.com"),
        json={
            "target_user_id": target_user["id"],
            "entitlement_id": 999999,
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Entitlement not found"}


def test_missing_user_returns_404_when_listing_access() -> None:
    response = client.get("/users/999999/access")

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}
