from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

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


def get_administrator() -> dict[str, Any]:
    return find_user_by_email("alice@example.com")


def get_help_desk_user() -> dict[str, Any]:
    return find_user_by_email("sarah@example.com")


def get_auditor() -> dict[str, Any]:
    return find_user_by_email("auditor@example.com")


def get_employee() -> dict[str, Any]:
    return find_user_by_email("bob@example.com")


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


def create_inactive_user(operator_role: str = "employee") -> dict[str, Any]:
    unique_email = f"inactive-{uuid4()}@example.com"
    response = client.post(
        "/users",
        json={
            "name": "Inactive User",
            "email": unique_email,
            "department": "Engineering",
            "active": False,
            "operator_role": operator_role,
        },
    )

    assert response.status_code == 201

    return response.json()


def get_audit_events(**filters: Any) -> list[dict[str, Any]]:
    response = client.get(
        "/audit-events",
        headers=auth_headers("alice@example.com"),
        params=filters,
    )

    assert response.status_code == 200

    return response.json()


def assert_audit_event_exists(
    *,
    requester_id: int,
    target_user_id: int,
    entitlement_id: int,
    action: str,
    result: str,
    reason: str | None = None,
) -> dict[str, Any]:
    events = get_audit_events(
        requester_id=requester_id,
        target_user_id=target_user_id,
        action=action,
        result=result,
    )

    for event in events:
        if event["entitlement_id"] != entitlement_id:
            continue

        if reason is not None and event["reason"] != reason:
            continue

        return event

    raise AssertionError(
        "Expected audit event was not found for "
        f"requester={requester_id}, target={target_user_id}, "
        f"entitlement={entitlement_id}, action={action}, result={result}"
    )


def test_inactive_target_users_are_denied_access() -> None:
    requester = get_administrator()
    target_user = create_inactive_user()
    entitlement = find_entitlement_by_slug("salesforce", "user")

    response = client.post(
        "/access/grant",
        headers=auth_headers(requester["email"]),
        json={
            "target_user_id": target_user["id"],
            "entitlement_id": entitlement["id"],
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Target user is inactive"}


def test_finance_portal_access_is_denied_to_non_finance_users() -> None:
    requester = get_administrator()
    target_user = get_employee()
    entitlement = find_entitlement_by_slug("finance-portal", "read-only")

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
        "detail": "Finance Portal access is restricted to Finance employees"
    }


def test_administrator_can_grant_administrator_access() -> None:
    requester = get_administrator()
    target_user = get_employee()
    entitlement = find_entitlement_by_slug("salesforce", "administrator")

    revoke_test_assignment(target_user["id"], entitlement["id"])

    try:
        response = client.post(
            "/access/grant",
            headers=auth_headers(requester["email"]),
            json={
                "target_user_id": target_user["id"],
                "entitlement_id": entitlement["id"],
            },
        )

        assert response.status_code == 201
        assert response.json()["entitlement"] == "Salesforce Administrator"
    finally:
        revoke_test_assignment(target_user["id"], entitlement["id"])


def test_help_desk_cannot_grant_administrator_access() -> None:
    requester = get_help_desk_user()
    target_user = get_employee()
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
    assert response.json() == {"detail": "Insufficient privileges"}


def test_help_desk_cannot_call_grant_endpoint() -> None:
    requester = get_help_desk_user()
    target_user = get_employee()
    entitlement = find_entitlement_by_slug("salesforce", "user")

    response = client.post(
        "/access/grant",
        headers=auth_headers(requester["email"]),
        json={
            "target_user_id": target_user["id"],
            "entitlement_id": entitlement["id"],
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient privileges"}


def test_auditor_cannot_grant_access() -> None:
    requester = get_auditor()
    target_user = get_employee()
    entitlement = find_entitlement_by_slug("salesforce", "user")

    response = client.post(
        "/access/grant",
        headers=auth_headers(requester["email"]),
        json={
            "target_user_id": target_user["id"],
            "entitlement_id": entitlement["id"],
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient privileges"}


def test_employee_cannot_grant_access() -> None:
    requester = get_employee()
    target_user = get_help_desk_user()
    entitlement = find_entitlement_by_slug("salesforce", "user")

    response = client.post(
        "/access/grant",
        headers=auth_headers(requester["email"]),
        json={
            "target_user_id": target_user["id"],
            "entitlement_id": entitlement["id"],
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient privileges"}


def test_denied_grant_requests_create_audit_events() -> None:
    requester = get_administrator()
    target_user = get_employee()
    entitlement = find_entitlement_by_slug("finance-portal", "read-only")

    response = client.post(
        "/access/grant",
        headers=auth_headers(requester["email"]),
        json={
            "target_user_id": target_user["id"],
            "entitlement_id": entitlement["id"],
        },
    )

    assert response.status_code == 403

    event = assert_audit_event_exists(
        requester_id=requester["id"],
        target_user_id=target_user["id"],
        entitlement_id=entitlement["id"],
        action="grant",
        result="denied",
        reason="Finance Portal access is restricted to Finance employees",
    )

    assert event["application"] == "Finance Portal"
    assert event["entitlement"] == "Finance Read Only"


def test_successful_grants_create_audit_events() -> None:
    requester = get_administrator()
    target_user = get_employee()
    entitlement = find_entitlement_by_slug("salesforce", "user")

    revoke_test_assignment(target_user["id"], entitlement["id"])

    try:
        response = client.post(
            "/access/grant",
            headers=auth_headers(requester["email"]),
            json={
                "target_user_id": target_user["id"],
                "entitlement_id": entitlement["id"],
            },
        )

        assert response.status_code == 201

        assert_audit_event_exists(
            requester_id=requester["id"],
            target_user_id=target_user["id"],
            entitlement_id=entitlement["id"],
            action="grant",
            result="succeeded",
            reason="Access request approved",
        )
    finally:
        revoke_test_assignment(target_user["id"], entitlement["id"])


def test_grant_audit_event_uses_request_correlation_id() -> None:
    requester = get_administrator()
    entitlement = find_entitlement_by_slug("salesforce", "user")
    unique_email = f"correlation-target-{uuid4()}@example.com"
    create_response = client.post(
        "/users",
        json={
            "name": "Correlation Target",
            "email": unique_email,
            "department": "Engineering",
            "active": True,
        },
    )
    assert create_response.status_code == 201
    target_user = create_response.json()
    correlation_id = f"audit-{uuid4()}"
    headers = auth_headers(requester["email"])
    headers["X-Correlation-ID"] = correlation_id

    try:
        response = client.post(
            "/access/grant",
            headers=headers,
            json={
                "target_user_id": target_user["id"],
                "entitlement_id": entitlement["id"],
            },
        )

        assert response.status_code == 201

        events = get_audit_events(correlation_id=correlation_id)
        assert any(
            event["requester_id"] == requester["id"]
            and event["target_user_id"] == target_user["id"]
            and event["entitlement_id"] == entitlement["id"]
            and event["action"] == "grant"
            and event["result"] == "succeeded"
            for event in events
        )
    finally:
        revoke_test_assignment(target_user["id"], entitlement["id"])


def test_successful_revokes_create_audit_events() -> None:
    requester = get_administrator()
    target_user = get_employee()
    entitlement = find_entitlement_by_slug("salesforce", "user")

    revoke_test_assignment(target_user["id"], entitlement["id"])
    grant_response = client.post(
        "/access/grant",
        headers=auth_headers(requester["email"]),
        json={
            "target_user_id": target_user["id"],
            "entitlement_id": entitlement["id"],
        },
    )
    revoke_response = client.post(
        "/access/revoke",
        headers=auth_headers(requester["email"]),
        json={
            "target_user_id": target_user["id"],
            "entitlement_id": entitlement["id"],
        },
    )

    assert grant_response.status_code == 201
    assert revoke_response.status_code == 200

    assert_audit_event_exists(
        requester_id=requester["id"],
        target_user_id=target_user["id"],
        entitlement_id=entitlement["id"],
        action="revoke",
        result="succeeded",
        reason="Access revoked",
    )


def test_denied_revokes_create_audit_events() -> None:
    administrator = get_administrator()
    requester = create_inactive_user(operator_role="security_admin")
    target_user = get_employee()
    entitlement = find_entitlement_by_slug("salesforce", "user")

    revoke_test_assignment(target_user["id"], entitlement["id"])

    try:
        grant_response = client.post(
            "/access/grant",
            headers=auth_headers(administrator["email"]),
            json={
                "target_user_id": target_user["id"],
                "entitlement_id": entitlement["id"],
            },
        )
        revoke_response = client.post(
            "/access/revoke",
            headers=auth_headers(requester["email"]),
            json={
                "target_user_id": target_user["id"],
                "entitlement_id": entitlement["id"],
            },
        )

        assert grant_response.status_code == 201
        assert revoke_response.status_code == 403
        assert revoke_response.json() == {"detail": "Requester is inactive"}

        assert_audit_event_exists(
            requester_id=requester["id"],
            target_user_id=target_user["id"],
            entitlement_id=entitlement["id"],
            action="revoke",
            result="denied",
            reason="Requester is inactive",
        )
    finally:
        revoke_test_assignment(target_user["id"], entitlement["id"])


def test_audit_filtering_by_requester_works() -> None:
    requester = get_administrator()
    events = get_audit_events(requester_id=requester["id"])

    assert events
    assert all(event["requester_id"] == requester["id"] for event in events)


def test_audit_filtering_by_target_user_works() -> None:
    target_user = get_employee()
    events = get_audit_events(target_user_id=target_user["id"])

    assert events
    assert all(event["target_user_id"] == target_user["id"] for event in events)


def test_audit_filtering_by_action_works() -> None:
    events = get_audit_events(action="grant")

    assert events
    assert all(event["action"] == "grant" for event in events)


def test_audit_filtering_by_result_works() -> None:
    events = get_audit_events(result="denied")

    assert events
    assert all(event["result"] == "denied" for event in events)


def test_missing_target_user_returns_404() -> None:
    requester = get_administrator()
    entitlement = find_entitlement_by_slug("salesforce", "user")

    response = client.post(
        "/access/grant",
        headers=auth_headers(requester["email"]),
        json={
            "target_user_id": 999999,
            "entitlement_id": entitlement["id"],
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


def test_missing_entitlement_returns_404() -> None:
    requester = get_administrator()
    target_user = get_employee()

    response = client.post(
        "/access/grant",
        headers=auth_headers(requester["email"]),
        json={
            "target_user_id": target_user["id"],
            "entitlement_id": 999999,
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Entitlement not found"}


def test_duplicate_grants_return_409_and_create_denied_audit_events() -> None:
    requester = get_administrator()
    target_user = get_employee()
    entitlement = find_entitlement_by_slug("salesforce", "user")

    revoke_test_assignment(target_user["id"], entitlement["id"])

    try:
        first_response = client.post(
            "/access/grant",
            headers=auth_headers(requester["email"]),
            json={
                "target_user_id": target_user["id"],
                "entitlement_id": entitlement["id"],
            },
        )
        second_response = client.post(
            "/access/grant",
            headers=auth_headers(requester["email"]),
            json={
                "target_user_id": target_user["id"],
                "entitlement_id": entitlement["id"],
            },
        )

        assert first_response.status_code == 201
        assert second_response.status_code == 409
        assert second_response.json() == {"detail": "User already has this access"}

        assert_audit_event_exists(
            requester_id=requester["id"],
            target_user_id=target_user["id"],
            entitlement_id=entitlement["id"],
            action="grant",
            result="denied",
            reason="User already has this access",
        )
    finally:
        revoke_test_assignment(target_user["id"], entitlement["id"])
