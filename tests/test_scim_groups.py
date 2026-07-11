from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

import app.scim.group_provisioning as group_provisioning
from app.domain.events import (
    GroupCreated,
    GroupMembershipAdded,
    GroupMembershipRemoved,
    GroupMembershipReplaced,
    GroupUpdated,
)
from app.domain.publisher import clear_published_events, get_published_events
from app.main import app
from app.scim.constants import (
    SCIM_MEDIA_TYPE,
    SCIM_SCHEMA_ERROR,
    SCIM_SCHEMA_GROUP,
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


def unique_group_name(prefix: str = "SCIM Group") -> str:
    return f"{prefix} {uuid4()}"


def seed_user(email: str) -> dict[str, Any]:
    response = client.get("/users")

    assert response.status_code == 200

    for user in response.json():
        if user["email"] == email:
            return user

    raise AssertionError(f"Seed user {email!r} was not found")


def group_payload(
    *,
    display_name: str | None = None,
    member_ids: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "schemas": [SCIM_SCHEMA_GROUP],
        "displayName": display_name or unique_group_name(),
        "members": [
            {"value": str(member_id)}
            for member_id in (member_ids or [])
        ],
    }


def patch_payload(*operations: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemas": [SCIM_PATCH_SCHEMA],
        "Operations": list(operations),
    }


def create_group(
    payload: dict[str, Any] | None = None,
    *,
    requester: str = "alice@example.com",
) -> Any:
    return client.post(
        "/scim/v2/Groups",
        headers=auth_headers(requester),
        json=payload or group_payload(),
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


def assert_group_audit_event(
    *,
    action: str,
    result: str,
    reason: str,
) -> dict[str, Any]:
    events = get_audit_events(action=action, result=result)
    for event in events:
        if event["reason"] != reason:
            continue

        assert event["application"] == "SCIM Provisioning"
        assert event["entitlement"] == "SCIM Group Lifecycle"
        return event

    raise AssertionError(f"Audit event {action}/{result}/{reason!r} not found")


def member_values(group: dict[str, Any]) -> set[str]:
    return {member["value"] for member in group["members"]}


def test_list_groups() -> None:
    created = create_group().json()

    response = client.get(
        "/scim/v2/Groups",
        headers=auth_headers("alice@example.com"),
        params={"filter": f'displayName eq "{created["displayName"]}"'},
    )

    assert response.status_code == 200
    assert_scim_media_type(response)
    assert response.json()["totalResults"] == 1
    assert any(group["id"] == created["id"] for group in response.json()["Resources"])


def test_lookup_group() -> None:
    alice = seed_user("alice@example.com")
    created = create_group(group_payload(member_ids=[alice["id"]])).json()

    response = client.get(
        f"/scim/v2/Groups/{created['id']}",
        headers=auth_headers("ian@example.com"),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["schemas"] == [SCIM_SCHEMA_GROUP]
    assert body["id"] == created["id"]
    assert body["displayName"] == created["displayName"]
    assert member_values(body) == {str(alice["id"])}
    assert body["meta"]["resourceType"] == "Group"


def test_create_group() -> None:
    alice = seed_user("alice@example.com")
    display_name = unique_group_name("Create Group")

    response = create_group(
        group_payload(display_name=display_name, member_ids=[alice["id"]])
    )

    assert response.status_code == 201
    assert response.headers["location"].endswith(
        f"/scim/v2/Groups/{response.json()['id']}"
    )
    assert response.json()["displayName"] == display_name
    assert member_values(response.json()) == {str(alice["id"])}


def test_duplicate_group() -> None:
    display_name = unique_group_name("Duplicate Group")
    first_response = create_group(group_payload(display_name=display_name))
    second_response = create_group(group_payload(display_name=display_name))

    assert first_response.status_code == 201
    assert_scim_error(
        second_response,
        status_code=409,
        scim_type="uniqueness",
    )


def test_put_replace() -> None:
    alice = seed_user("alice@example.com")
    bob = seed_user("bob@example.com")
    created = create_group(group_payload(member_ids=[alice["id"]])).json()
    new_display_name = unique_group_name("PUT Group")

    response = client.put(
        f"/scim/v2/Groups/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=group_payload(
            display_name=new_display_name,
            member_ids=[bob["id"]],
        ),
    )

    assert response.status_code == 200
    assert response.json()["displayName"] == new_display_name
    assert member_values(response.json()) == {str(bob["id"])}


def test_patch_display_name() -> None:
    created = create_group().json()
    new_display_name = unique_group_name("Patched Group")

    response = client.patch(
        f"/scim/v2/Groups/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "replace",
                "path": "displayName",
                "value": new_display_name,
            }
        ),
    )

    assert response.status_code == 200
    assert response.json()["displayName"] == new_display_name


def test_patch_add_member() -> None:
    bob = seed_user("bob@example.com")
    created = create_group().json()

    response = client.patch(
        f"/scim/v2/Groups/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "add",
                "path": "members",
                "value": {"value": str(bob["id"])},
            }
        ),
    )

    assert response.status_code == 200
    assert str(bob["id"]) in member_values(response.json())


def test_patch_remove_member() -> None:
    bob = seed_user("bob@example.com")
    created = create_group(group_payload(member_ids=[bob["id"]])).json()

    response = client.patch(
        f"/scim/v2/Groups/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "remove",
                "path": "members",
                "value": {"value": str(bob["id"])},
            }
        ),
    )

    assert response.status_code == 200
    assert str(bob["id"]) not in member_values(response.json())


def test_patch_replace_members() -> None:
    alice = seed_user("alice@example.com")
    bob = seed_user("bob@example.com")
    ian = seed_user("ian@example.com")
    created = create_group(group_payload(member_ids=[alice["id"]])).json()

    response = client.patch(
        f"/scim/v2/Groups/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "replace",
                "path": "members",
                "value": [
                    {"value": str(bob["id"])},
                    {"value": str(ian["id"])},
                ],
            }
        ),
    )

    assert response.status_code == 200
    assert member_values(response.json()) == {str(bob["id"]), str(ian["id"])}


def test_list_members() -> None:
    alice = seed_user("alice@example.com")
    bob = seed_user("bob@example.com")
    created = create_group(
        group_payload(member_ids=[alice["id"], bob["id"]])
    ).json()

    response = client.get(
        f"/scim/v2/Groups/{created['id']}",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 200
    assert member_values(response.json()) == {str(alice["id"]), str(bob["id"])}


def test_duplicate_member_rejected() -> None:
    alice = seed_user("alice@example.com")

    response = create_group(
        group_payload(member_ids=[alice["id"], alice["id"]])
    )

    assert_scim_error(response, status_code=409, scim_type="uniqueness")


def test_unknown_member() -> None:
    response = create_group(group_payload(member_ids=[999999]))

    assert_scim_error(response, status_code=400, scim_type="invalidValue")


def test_unknown_group() -> None:
    response = client.get(
        "/scim/v2/Groups/999999",
        headers=auth_headers("alice@example.com"),
    )

    assert_scim_error(response, status_code=404)


def test_malformed_patch() -> None:
    created = create_group().json()

    response = client.patch(
        f"/scim/v2/Groups/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json={
            "schemas": [SCIM_PATCH_SCHEMA],
            "Operations": "not-an-array",
        },
    )

    assert_scim_error(response, status_code=400, scim_type="invalidValue")


def test_invalid_payload() -> None:
    response = create_group(
        {
            "schemas": [SCIM_SCHEMA_GROUP],
            "displayName": 123,
            "members": "not-an-array",
        }
    )

    assert_scim_error(response, status_code=400, scim_type="invalidValue")


def test_filtering() -> None:
    display_name = unique_group_name("Filter Admin")
    create_group(group_payload(display_name=display_name))

    response = client.get(
        "/scim/v2/Groups",
        headers=auth_headers("alice@example.com"),
        params={"filter": f'displayName eq "{display_name}"'},
    )

    assert response.status_code == 200
    assert response.json()["totalResults"] == 1
    assert response.json()["Resources"][0]["displayName"] == display_name


def test_sorting() -> None:
    create_group(group_payload(display_name=unique_group_name("AAA Group")))
    create_group(group_payload(display_name=unique_group_name("ZZZ Group")))

    response = client.get(
        "/scim/v2/Groups",
        headers=auth_headers("alice@example.com"),
        params={
            "sortBy": "displayName",
            "sortOrder": "ascending",
            "count": "5",
        },
    )

    assert response.status_code == 200

    display_names = [
        group["displayName"] for group in response.json()["Resources"]
    ]

    assert display_names == sorted(display_names, key=str.lower)


def test_pagination() -> None:
    create_group()
    create_group()

    response = client.get(
        "/scim/v2/Groups",
        headers=auth_headers("alice@example.com"),
        params={
            "sortBy": "id",
            "startIndex": "2",
            "count": "1",
        },
    )

    assert response.status_code == 200
    assert response.json()["startIndex"] == 2
    assert response.json()["itemsPerPage"] == 1


def test_attribute_projection() -> None:
    created = create_group().json()

    response = client.get(
        f"/scim/v2/Groups/{created['id']}",
        headers=auth_headers("alice@example.com"),
        params={"attributes": "displayName"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "schemas": [SCIM_SCHEMA_GROUP],
        "id": created["id"],
        "displayName": created["displayName"],
    }


def test_scim_400() -> None:
    created = create_group().json()

    response = client.patch(
        f"/scim/v2/Groups/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "replace",
                "path": "unsupported",
                "value": "bad",
            }
        ),
    )

    assert_scim_error(response, status_code=400, scim_type="invalidPath")


def test_scim_404() -> None:
    response = client.patch(
        "/scim/v2/Groups/999999",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "replace",
                "path": "displayName",
                "value": unique_group_name("Missing"),
            }
        ),
    )

    assert_scim_error(response, status_code=404)


def test_scim_409() -> None:
    display_name = unique_group_name("Conflict Group")
    first_response = create_group(group_payload(display_name=display_name))
    second_response = create_group(group_payload(display_name=display_name))

    assert first_response.status_code == 201
    assert_scim_error(second_response, status_code=409, scim_type="uniqueness")


def test_unauthorized_request() -> None:
    response = client.get("/scim/v2/Groups")

    assert_scim_error(response, status_code=401)


def test_helpdesk_forbidden() -> None:
    response = create_group(requester="sarah@example.com")

    assert_scim_error(response, status_code=403)


def test_employee_forbidden() -> None:
    response = create_group(requester="bob@example.com")

    assert_scim_error(response, status_code=403)


def test_iam_admin_success() -> None:
    response = create_group(requester="ian@example.com")

    assert response.status_code == 201


def test_security_admin_success() -> None:
    response = create_group(requester="alice@example.com")

    assert response.status_code == 201


def test_audit_events_created() -> None:
    response = create_group(group_payload(display_name=unique_group_name("Audit")))

    assert response.status_code == 201

    event = assert_group_audit_event(
        action="scim_group_create",
        result="succeeded",
        reason="Group created",
    )

    assert event["application"] == "SCIM Provisioning"


def test_rollback_on_audit_failure(monkeypatch: Any) -> None:
    clear_published_events()
    display_name = unique_group_name("Rollback Group")

    def fail_audit(*args: Any, **kwargs: Any) -> None:
        raise SQLAlchemyError("audit failed")

    monkeypatch.setattr(group_provisioning, "create_audit_event", fail_audit)

    response = create_group(group_payload(display_name=display_name))

    assert_scim_error(response, status_code=500)
    assert get_published_events() == []

    lookup = client.get(
        "/scim/v2/Groups",
        headers=auth_headers("alice@example.com"),
        params={"filter": f'displayName eq "{display_name}"'},
    )

    assert lookup.status_code == 200
    assert lookup.json()["totalResults"] == 0


def test_domain_event_group_creation() -> None:
    clear_published_events()

    response = create_group()

    assert response.status_code == 201
    assert any(isinstance(event, GroupCreated) for event in get_published_events())


def test_domain_event_rename() -> None:
    created = create_group().json()
    clear_published_events()

    response = client.patch(
        f"/scim/v2/Groups/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "replace",
                "path": "displayName",
                "value": unique_group_name("Event Rename"),
            }
        ),
    )

    assert response.status_code == 200
    assert any(isinstance(event, GroupUpdated) for event in get_published_events())


def test_domain_event_add_member() -> None:
    bob = seed_user("bob@example.com")
    created = create_group().json()
    clear_published_events()

    response = client.patch(
        f"/scim/v2/Groups/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "add",
                "path": "members",
                "value": {"value": str(bob["id"])},
            }
        ),
    )

    assert response.status_code == 200
    assert any(
        isinstance(event, GroupMembershipAdded)
        for event in get_published_events()
    )


def test_domain_event_remove_member() -> None:
    bob = seed_user("bob@example.com")
    created = create_group(group_payload(member_ids=[bob["id"]])).json()
    clear_published_events()

    response = client.patch(
        f"/scim/v2/Groups/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "remove",
                "path": "members",
                "value": {"value": str(bob["id"])},
            }
        ),
    )

    assert response.status_code == 200
    assert any(
        isinstance(event, GroupMembershipRemoved)
        for event in get_published_events()
    )


def test_domain_event_replace_members() -> None:
    alice = seed_user("alice@example.com")
    bob = seed_user("bob@example.com")
    created = create_group(group_payload(member_ids=[alice["id"]])).json()
    clear_published_events()

    response = client.patch(
        f"/scim/v2/Groups/{created['id']}",
        headers=auth_headers("alice@example.com"),
        json=patch_payload(
            {
                "op": "replace",
                "path": "members",
                "value": [{"value": str(bob["id"])}],
            }
        ),
    )

    assert response.status_code == 200
    assert any(
        isinstance(event, GroupMembershipReplaced)
        for event in get_published_events()
    )


def test_openapi_documents_group_endpoints() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200

    schema = response.json()
    groups_path = schema["paths"]["/scim/v2/Groups"]
    group_path = schema["paths"]["/scim/v2/Groups/{group_id}"]

    assert groups_path["get"]["summary"] == "List SCIM groups"
    assert groups_path["post"]["summary"] == "Create a SCIM group"
    assert group_path["get"]["summary"] == "Get a SCIM group"
    assert group_path["put"]["summary"] == "Replace a SCIM group"
    assert group_path["patch"]["summary"] == "Patch a SCIM group"
    assert "requestBody" in groups_path["post"]
    assert "requestBody" in group_path["patch"]
