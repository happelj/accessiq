from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

import app.scim.provisioning as provisioning
from app.main import app
from app.scim.constants import (
    SCIM_MEDIA_TYPE,
    SCIM_SCHEMA_ERROR,
    SCIM_SCHEMA_USER,
)
from app.scim.provisioning import SCIM_PATCH_SCHEMA

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


def unique_email(prefix: str = "scim-provisioning") -> str:
    return f"{prefix}-{uuid4()}@example.com"


def scim_user_payload(
    *,
    email: str | None = None,
    display_name: str = "SCIM Provisioned User",
    active: bool = True,
) -> dict[str, Any]:
    return {
        "schemas": [SCIM_SCHEMA_USER],
        "userName": email or unique_email(),
        "displayName": display_name,
        "active": active,
    }


def patch_payload(*operations: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemas": [SCIM_PATCH_SCHEMA],
        "Operations": list(operations),
    }


def create_scim_user(
    payload: dict[str, Any] | None = None,
    *,
    requester: str = "alice@example.com",
) -> Any:
    return client.post(
        "/scim/v2/Users",
        headers=auth_headers(requester),
        json=payload or scim_user_payload(),
    )


def assert_scim_media_type(response: Any) -> None:
    assert response.headers["content-type"].startswith(SCIM_MEDIA_TYPE)


def assert_scim_error(
    response: Any,
    *,
    status_code: int,
    scim_type: str | None = None,
) -> None:
    assert response.status_code == status_code
    assert_scim_media_type(response)
    assert response.json()["schemas"] == [SCIM_SCHEMA_ERROR]
    assert response.json()["status"] == str(status_code)
    if scim_type is not None:
        assert response.json()["scimType"] == scim_type


def get_audit_events(**params: Any) -> list[dict[str, Any]]:
    response = client.get(
        "/audit-events",
        headers=auth_headers("alice@example.com"),
        params=params,
    )

    assert response.status_code == 200

    return response.json()


def assert_audit_event(
    *,
    action: str,
    result: str,
    reason: str,
    target_user_id: int | None = None,
) -> dict[str, Any]:
    events = get_audit_events(action=action, result=result)
    for event in events:
        if event["reason"] != reason:
            continue

        if target_user_id is not None and event["target_user_id"] != target_user_id:
            continue

        assert event["application"] == "SCIM Provisioning"
        assert event["entitlement"] == "SCIM User Lifecycle"
        return event

    raise AssertionError(f"Audit event {action}/{result}/{reason!r} not found")


def find_rest_user(email: str) -> dict[str, Any] | None:
    response = client.get("/users")

    assert response.status_code == 200

    for user in response.json():
        if user["email"] == email:
            return user

    return None


def test_create_user() -> None:
    email = unique_email()

    response = create_scim_user(
        scim_user_payload(
            email=email,
            display_name="Create SCIM User",
        )
    )

    assert response.status_code == 201
    assert_scim_media_type(response)

    body = response.json()

    assert response.headers["location"].endswith(f"/scim/v2/Users/{body['id']}")
    assert body["schemas"] == [SCIM_SCHEMA_USER]
    assert body["userName"] == email
    assert body["displayName"] == "Create SCIM User"
    assert body["active"] is True


def test_duplicate_user() -> None:
    email = unique_email()
    first_response = create_scim_user(scim_user_payload(email=email))
    second_response = create_scim_user(scim_user_payload(email=email))

    assert first_response.status_code == 201
    assert_scim_error(
        second_response,
        status_code=409,
        scim_type="uniqueness",
    )
    assert second_response.json()["detail"] == "Duplicate userName"


def test_put_update() -> None:
    created = create_scim_user().json()
    new_email = unique_email("scim-put")

    response = client.put(
        f"/scim/v2/Users/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=scim_user_payload(
            email=new_email,
            display_name="PUT Updated User",
            active=True,
        ),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == created["id"]
    assert body["userName"] == new_email
    assert body["displayName"] == "PUT Updated User"
    assert body["active"] is True


def test_patch_replace() -> None:
    created = create_scim_user().json()

    response = client.patch(
        f"/scim/v2/Users/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "replace",
                "path": "displayName",
                "value": "Patched Display Name",
            }
        ),
    )

    assert response.status_code == 200
    assert response.json()["displayName"] == "Patched Display Name"


def test_patch_add() -> None:
    created = create_scim_user().json()
    new_email = unique_email("scim-patch-add")

    response = client.patch(
        f"/scim/v2/Users/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "add",
                "path": "userName",
                "value": new_email,
            }
        ),
    )

    assert response.status_code == 200
    assert response.json()["userName"] == new_email


def test_patch_remove() -> None:
    created = create_scim_user(active_payload := scim_user_payload(active=True)).json()
    assert active_payload["active"] is True

    response = client.patch(
        f"/scim/v2/Users/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "remove",
                "path": "active",
            }
        ),
    )

    assert response.status_code == 200
    assert response.json()["active"] is False


def test_deactivate_user() -> None:
    created = create_scim_user().json()

    response = client.put(
        f"/scim/v2/Users/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=scim_user_payload(
            email=created["userName"],
            display_name=created["displayName"],
            active=False,
        ),
    )

    assert response.status_code == 200
    assert response.json()["active"] is False


def test_active_true() -> None:
    response = create_scim_user(scim_user_payload(active=True))

    assert response.status_code == 201
    assert response.json()["active"] is True


def test_active_false() -> None:
    response = create_scim_user(scim_user_payload(active=False))

    assert response.status_code == 201
    assert response.json()["active"] is False


def test_malformed_patch() -> None:
    created = create_scim_user().json()

    response = client.patch(
        f"/scim/v2/Users/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json={
            "schemas": [SCIM_PATCH_SCHEMA],
            "Operations": "not-an-array",
        },
    )

    assert_scim_error(response, status_code=400, scim_type="invalidValue")


def test_unsupported_patch_operation() -> None:
    created = create_scim_user().json()

    response = client.patch(
        f"/scim/v2/Users/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "move",
                "path": "displayName",
                "value": "Moved User",
            }
        ),
    )

    assert_scim_error(response, status_code=400, scim_type="invalidValue")


def test_unsupported_patch_path() -> None:
    created = create_scim_user().json()

    response = client.patch(
        f"/scim/v2/Users/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "replace",
                "path": "phoneNumbers",
                "value": "555-0100",
            }
        ),
    )

    assert_scim_error(response, status_code=400, scim_type="invalidPath")


def test_invalid_payload() -> None:
    response = create_scim_user(
        {
            "schemas": [SCIM_SCHEMA_USER],
            "userName": "not-an-email",
            "displayName": "Invalid User",
            "active": "yes",
        }
    )

    assert_scim_error(response, status_code=400, scim_type="invalidValue")


def test_missing_required_fields() -> None:
    response = create_scim_user(
        {
            "schemas": [SCIM_SCHEMA_USER],
            "displayName": "Missing User Name",
            "active": True,
        }
    )

    assert_scim_error(response, status_code=400, scim_type="invalidValue")
    assert response.json()["detail"] == "userName is required"


def test_duplicate_username_on_patch() -> None:
    first = create_scim_user().json()
    second = create_scim_user().json()

    response = client.patch(
        f"/scim/v2/Users/{second['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "replace",
                "path": "userName",
                "value": first["userName"],
            }
        ),
    )

    assert_scim_error(response, status_code=409, scim_type="uniqueness")


def test_unknown_user() -> None:
    response = client.put(
        "/scim/v2/Users/999999",
        headers=auth_headers("alice@example.com"),
        json=scim_user_payload(),
    )

    assert_scim_error(response, status_code=404)


def test_scim_404() -> None:
    response = client.patch(
        "/scim/v2/Users/999999",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "replace",
                "path": "active",
                "value": False,
            }
        ),
    )

    assert_scim_error(response, status_code=404)
    assert response.json()["detail"] == "User 999999 not found"


def test_scim_409() -> None:
    email = unique_email()
    first_response = create_scim_user(scim_user_payload(email=email))
    second_response = create_scim_user(scim_user_payload(email=email))

    assert first_response.status_code == 201
    assert_scim_error(second_response, status_code=409, scim_type="uniqueness")


def test_audit_event_created() -> None:
    response = create_scim_user(scim_user_payload(display_name="Audited SCIM User"))

    assert response.status_code == 201

    body = response.json()
    event = assert_audit_event(
        action="scim_user_create",
        result="succeeded",
        reason="User created",
        target_user_id=int(body["id"]),
    )

    assert event["target_user_id"] == int(body["id"])


def test_audit_failure_handling(monkeypatch: Any) -> None:
    email = unique_email("audit-failure")

    def fail_audit(*args: Any, **kwargs: Any) -> None:
        raise SQLAlchemyError("audit failed")

    monkeypatch.setattr(provisioning, "create_audit_event", fail_audit)

    response = create_scim_user(scim_user_payload(email=email))

    assert_scim_error(response, status_code=500)
    assert find_rest_user(email) is None


def test_unauthorized_request() -> None:
    response = client.post(
        "/scim/v2/Users",
        json=scim_user_payload(),
    )

    assert_scim_error(response, status_code=401)


def test_helpdesk_forbidden() -> None:
    response = create_scim_user(requester="sarah@example.com")

    assert_scim_error(response, status_code=403)


def test_employee_forbidden() -> None:
    response = create_scim_user(requester="bob@example.com")

    assert_scim_error(response, status_code=403)


def test_iam_admin_success() -> None:
    response = create_scim_user(requester="ian@example.com")

    assert response.status_code == 201


def test_security_admin_success() -> None:
    response = create_scim_user(requester="alice@example.com")

    assert response.status_code == 201


def test_openapi_documents_provisioning_endpoints() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200

    schema = response.json()
    users_path = schema["paths"]["/scim/v2/Users"]
    user_path = schema["paths"]["/scim/v2/Users/{user_id}"]

    assert users_path["post"]["summary"] == "Create a SCIM user"
    assert "requestBody" in users_path["post"]
    assert user_path["put"]["summary"] == "Replace a SCIM user"
    assert "requestBody" in user_path["put"]
    assert user_path["patch"]["summary"] == "Patch a SCIM user"
    assert "requestBody" in user_path["patch"]
