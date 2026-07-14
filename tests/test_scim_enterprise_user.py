from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

import app.scim.provisioning as provisioning
from app.domain.events import (
    DepartmentChanged,
    EmployeeNumberChanged,
    EnterpriseProfileCreated,
    ManagerChanged,
    OrganizationChanged,
)
from app.domain.publisher import clear_published_events, get_published_events
from app.main import app
from app.scim.constants import (
    SCIM_MEDIA_TYPE,
    SCIM_SCHEMA_ENTERPRISE_USER,
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


def unique_email(prefix: str = "enterprise") -> str:
    return f"{prefix}-{uuid4()}@example.com"


def unique_employee_number(prefix: str = "E") -> str:
    return f"{prefix}-{uuid4()}"


def seed_user(email: str) -> dict[str, Any]:
    response = client.get("/users")

    assert response.status_code == 200

    for user in response.json():
        if user["email"] == email:
            return user

    raise AssertionError(f"Seed user {email!r} was not found")


def enterprise_extension(
    *,
    employee_number: str | None = None,
    department: str = "Engineering",
    division: str = "Platform",
    organization: str = "AccessIQ",
    cost_center: str = "ENG-001",
    manager_id: int | None = None,
) -> dict[str, Any]:
    extension: dict[str, Any] = {
        "employeeNumber": employee_number or unique_employee_number(),
        "department": department,
        "division": division,
        "organization": organization,
        "costCenter": cost_center,
    }
    if manager_id is not None:
        extension["manager"] = {"value": str(manager_id)}

    return extension


def scim_user_payload(
    *,
    email: str | None = None,
    display_name: str = "Enterprise SCIM User",
    active: bool = True,
    enterprise: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schemas": [SCIM_SCHEMA_USER],
        "userName": email or unique_email(),
        "displayName": display_name,
        "active": active,
    }
    if enterprise is not None:
        payload["schemas"] = [SCIM_SCHEMA_USER, SCIM_SCHEMA_ENTERPRISE_USER]
        payload[SCIM_SCHEMA_ENTERPRISE_USER] = enterprise

    return payload


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


def assert_enterprise_audit_event(
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
        assert event["entitlement"] == "SCIM Enterprise User Extension"
        return event

    raise AssertionError(f"Audit event {action}/{result}/{reason!r} not found")


def find_rest_user(email: str) -> dict[str, Any] | None:
    response = client.get("/users")

    assert response.status_code == 200

    for user in response.json():
        if user["email"] == email:
            return user

    return None


def enterprise_part(resource: dict[str, Any]) -> dict[str, Any]:
    return resource[SCIM_SCHEMA_ENTERPRISE_USER]


def test_create_enterprise_profile() -> None:
    employee_number = unique_employee_number()

    response = create_scim_user(
        scim_user_payload(
            enterprise=enterprise_extension(employee_number=employee_number)
        )
    )

    assert response.status_code == 201
    assert_scim_media_type(response)

    body = response.json()
    extension = enterprise_part(body)

    assert body["schemas"] == [SCIM_SCHEMA_USER, SCIM_SCHEMA_ENTERPRISE_USER]
    assert extension["employeeNumber"] == employee_number
    assert extension["department"] == "Engineering"
    assert extension["division"] == "Platform"
    assert extension["organization"] == "AccessIQ"
    assert extension["costCenter"] == "ENG-001"


def test_read_enterprise_profile() -> None:
    employee_number = unique_employee_number()
    created = create_scim_user(
        scim_user_payload(
            enterprise=enterprise_extension(employee_number=employee_number)
        )
    ).json()

    response = client.get(
        f"/scim/v2/Users/{created['id']}",
        headers=auth_headers("ian@example.com"),
    )

    assert response.status_code == 200
    assert enterprise_part(response.json())["employeeNumber"] == employee_number


def test_update_enterprise_profile() -> None:
    created = create_scim_user(
        scim_user_payload(enterprise=enterprise_extension())
    ).json()

    response = client.patch(
        f"/scim/v2/Users/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "replace",
                "path": f"{SCIM_SCHEMA_ENTERPRISE_USER}:department",
                "value": "Finance",
            }
        ),
    )

    assert response.status_code == 200
    assert enterprise_part(response.json())["department"] == "Finance"


def test_put_replacement() -> None:
    created = create_scim_user(
        scim_user_payload(enterprise=enterprise_extension())
    ).json()
    new_employee_number = unique_employee_number("PUT")

    response = client.put(
        f"/scim/v2/Users/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=scim_user_payload(
            email=created["userName"],
            display_name="Enterprise PUT User",
            enterprise={
                "employeeNumber": new_employee_number,
                "department": "Operations",
            },
        ),
    )

    assert response.status_code == 200

    extension = enterprise_part(response.json())
    assert extension["employeeNumber"] == new_employee_number
    assert extension["department"] == "Operations"
    assert "division" not in extension
    assert "organization" not in extension
    assert "costCenter" not in extension


def test_patch_add() -> None:
    created = create_scim_user().json()

    response = client.patch(
        f"/scim/v2/Users/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "add",
                "path": "costCenter",
                "value": "FIN-010",
            }
        ),
    )

    assert response.status_code == 200
    assert enterprise_part(response.json())["costCenter"] == "FIN-010"


def test_patch_replace() -> None:
    created = create_scim_user(
        scim_user_payload(enterprise=enterprise_extension())
    ).json()

    response = client.patch(
        f"/scim/v2/Users/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "replace",
                "path": "organization",
                "value": "AccessIQ Labs",
            }
        ),
    )

    assert response.status_code == 200
    assert enterprise_part(response.json())["organization"] == "AccessIQ Labs"


def test_patch_remove() -> None:
    created = create_scim_user(
        scim_user_payload(enterprise=enterprise_extension(cost_center="OPS-100"))
    ).json()

    response = client.patch(
        f"/scim/v2/Users/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "remove",
                "path": "costCenter",
            }
        ),
    )

    assert response.status_code == 200
    assert "costCenter" not in enterprise_part(response.json())


def test_manager_assignment() -> None:
    manager = seed_user("manager@example.com")

    response = create_scim_user(
        scim_user_payload(enterprise=enterprise_extension(manager_id=manager["id"]))
    )

    assert response.status_code == 201

    manager_value = enterprise_part(response.json())["manager"]
    assert manager_value["value"] == str(manager["id"])
    assert manager_value["displayName"] == manager["name"]
    assert manager_value["$ref"].endswith(f"/scim/v2/Users/{manager['id']}")


def test_unknown_manager() -> None:
    response = create_scim_user(
        scim_user_payload(enterprise=enterprise_extension(manager_id=999999))
    )

    assert_scim_error(response, status_code=400, scim_type="invalidValue")
    assert response.json()["detail"] == "Unknown manager"


def test_self_manager_rejection() -> None:
    created = create_scim_user().json()

    response = client.patch(
        f"/scim/v2/Users/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "replace",
                "path": "manager",
                "value": {"value": created["id"]},
            }
        ),
    )

    assert_scim_error(response, status_code=400, scim_type="invalidValue")
    assert response.json()["detail"] == "Self manager is not allowed"


def test_circular_manager_rejection() -> None:
    manager = create_scim_user().json()
    report = create_scim_user().json()

    first_response = client.patch(
        f"/scim/v2/Users/{manager['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "replace",
                "path": "manager",
                "value": {"value": report["id"]},
            }
        ),
    )

    assert first_response.status_code == 200

    second_response = client.patch(
        f"/scim/v2/Users/{report['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "replace",
                "path": "manager",
                "value": {"value": manager["id"]},
            }
        ),
    )

    assert_scim_error(second_response, status_code=400, scim_type="invalidValue")
    assert second_response.json()["detail"] == "Manager cycle detected"


def test_duplicate_employee_number() -> None:
    employee_number = unique_employee_number("DUP")
    first_response = create_scim_user(
        scim_user_payload(
            enterprise=enterprise_extension(employee_number=employee_number)
        )
    )
    second_response = create_scim_user(
        scim_user_payload(
            enterprise=enterprise_extension(employee_number=employee_number)
        )
    )

    assert first_response.status_code == 201
    assert_scim_error(second_response, status_code=409, scim_type="uniqueness")
    assert second_response.json()["detail"] == "Duplicate employeeNumber"


def test_malformed_enterprise_payload() -> None:
    response = create_scim_user(
        {
            **scim_user_payload(),
            "schemas": [SCIM_SCHEMA_USER, SCIM_SCHEMA_ENTERPRISE_USER],
            SCIM_SCHEMA_ENTERPRISE_USER: "not-an-object",
        }
    )

    assert_scim_error(response, status_code=400, scim_type="invalidValue")


def test_patch_validation() -> None:
    created = create_scim_user().json()

    response = client.patch(
        f"/scim/v2/Users/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "replace",
                "path": f"{SCIM_SCHEMA_ENTERPRISE_USER}:location",
                "value": "HQ",
            }
        ),
    )

    assert_scim_error(response, status_code=400, scim_type="invalidPath")


def test_scim_400() -> None:
    response = create_scim_user(
        scim_user_payload(enterprise={"manager": {"displayName": "No ID"}})
    )

    assert_scim_error(response, status_code=400, scim_type="invalidValue")


def test_scim_404() -> None:
    response = client.put(
        "/scim/v2/Users/999999",
        headers=auth_headers("alice@example.com"),
        json=scim_user_payload(enterprise=enterprise_extension()),
    )

    assert_scim_error(response, status_code=404)


def test_scim_409() -> None:
    employee_number = unique_employee_number("CONFLICT")
    first_response = create_scim_user(
        scim_user_payload(
            enterprise=enterprise_extension(employee_number=employee_number)
        )
    )
    second_response = create_scim_user(
        scim_user_payload(
            enterprise=enterprise_extension(employee_number=employee_number)
        )
    )

    assert first_response.status_code == 201
    assert_scim_error(second_response, status_code=409, scim_type="uniqueness")


def test_audit_events() -> None:
    response = create_scim_user(
        scim_user_payload(enterprise=enterprise_extension(department="Audit"))
    )

    assert response.status_code == 201

    body = response.json()
    assert_enterprise_audit_event(
        action="scim_enterprise_profile_create",
        result="succeeded",
        reason="Enterprise profile created",
        target_user_id=int(body["id"]),
    )
    assert_enterprise_audit_event(
        action="scim_enterprise_department_change",
        result="succeeded",
        reason="Department changed",
        target_user_id=int(body["id"]),
    )


def test_rollback_on_audit_failure(monkeypatch: Any) -> None:
    email = unique_email("enterprise-audit-failure")

    def fail_audit(*args: Any, **kwargs: Any) -> None:
        raise SQLAlchemyError("audit failed")

    monkeypatch.setattr(provisioning, "create_audit_event", fail_audit)

    response = create_scim_user(
        scim_user_payload(
            email=email,
            enterprise=enterprise_extension(),
        )
    )

    assert_scim_error(response, status_code=500)
    assert find_rest_user(email) is None


def test_domain_events() -> None:
    clear_published_events()
    manager = seed_user("manager@example.com")
    employee_number = unique_employee_number("EVENT")

    response = create_scim_user(
        scim_user_payload(
            enterprise=enterprise_extension(
                employee_number=employee_number,
                department="Events",
                organization="Event Org",
                manager_id=manager["id"],
            )
        )
    )

    assert response.status_code == 201

    events = get_published_events()
    assert any(isinstance(event, EnterpriseProfileCreated) for event in events)
    assert any(
        isinstance(event, EmployeeNumberChanged)
        and event.employee_number == employee_number
        for event in events
    )
    assert any(
        isinstance(event, DepartmentChanged) and event.department == "Events"
        for event in events
    )
    assert any(
        isinstance(event, OrganizationChanged) and event.organization == "Event Org"
        for event in events
    )
    assert any(
        isinstance(event, ManagerChanged) and event.manager_id == manager["id"]
        for event in events
    )


def test_unauthorized() -> None:
    response = client.post(
        "/scim/v2/Users",
        json=scim_user_payload(enterprise=enterprise_extension()),
    )

    assert_scim_error(response, status_code=401)


def test_helpdesk_forbidden() -> None:
    response = create_scim_user(
        scim_user_payload(enterprise=enterprise_extension()),
        requester="sarah@example.com",
    )

    assert_scim_error(response, status_code=403)


def test_employee_forbidden() -> None:
    response = create_scim_user(
        scim_user_payload(enterprise=enterprise_extension()),
        requester="bob@example.com",
    )

    assert_scim_error(response, status_code=403)


def test_iam_admin_success() -> None:
    response = create_scim_user(
        scim_user_payload(enterprise=enterprise_extension()),
        requester="ian@example.com",
    )

    assert response.status_code == 201


def test_security_admin_success() -> None:
    response = create_scim_user(
        scim_user_payload(enterprise=enterprise_extension()),
        requester="alice@example.com",
    )

    assert response.status_code == 201


def test_openapi_documents_enterprise_examples() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200

    schema = response.json()
    user_post_examples = schema["paths"]["/scim/v2/Users"]["post"]["requestBody"][
        "content"
    ][SCIM_MEDIA_TYPE]["examples"]
    user_patch_examples = schema["paths"]["/scim/v2/Users/{user_id}"]["patch"][
        "requestBody"
    ]["content"][SCIM_MEDIA_TYPE]["examples"]

    assert "enterprise-user" in user_post_examples
    assert "replace-enterprise-department" in user_patch_examples
    assert "replace-manager" in user_patch_examples
