from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.scim.constants import (
    SCIM_MEDIA_TYPE,
    SCIM_SCHEMA_ERROR,
    SCIM_SCHEMA_LIST_RESPONSE,
    SCIM_SCHEMA_USER,
)

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


def assert_scim_media_type(response: Any) -> None:
    assert response.headers["content-type"].startswith(SCIM_MEDIA_TYPE)


def find_rest_user(email: str) -> dict[str, Any]:
    response = client.get("/users")

    assert response.status_code == 200

    for user in response.json():
        if user["email"] == email:
            return user

    raise AssertionError(f"User with email {email!r} was not found")


def create_user(*, name: str, active: bool = True) -> dict[str, Any]:
    response = client.post(
        "/users",
        json={
            "name": name,
            "email": f"scim-{uuid4()}@example.com",
            "department": "Engineering",
            "active": active,
            "operator_role": "employee",
        },
    )

    assert response.status_code == 201

    return response.json()


def get_scim_users(params: dict[str, str] | None = None) -> Any:
    return client.get(
        "/scim/v2/Users",
        headers=auth_headers("alice@example.com"),
        params=params,
    )


def test_get_users_returns_list_response() -> None:
    response = get_scim_users()

    assert response.status_code == 200
    assert_scim_media_type(response)

    body = response.json()

    assert body["schemas"] == [SCIM_SCHEMA_LIST_RESPONSE]
    assert body["totalResults"] >= 1
    assert body["startIndex"] == 1
    assert body["itemsPerPage"] == len(body["Resources"])
    assert body["Resources"][0]["schemas"] == [SCIM_SCHEMA_USER]
    assert isinstance(body["Resources"][0]["id"], str)
    assert body["Resources"][0]["userName"]
    assert body["Resources"][0]["meta"]["resourceType"] == "User"


def test_get_user_by_id_returns_scim_user() -> None:
    rest_user = find_rest_user("alice@example.com")

    response = client.get(
        f"/scim/v2/Users/{rest_user['id']}",
        headers=auth_headers("ian@example.com"),
    )

    assert response.status_code == 200
    assert_scim_media_type(response)

    body = response.json()

    assert body["schemas"] == [SCIM_SCHEMA_USER]
    assert body["id"] == str(rest_user["id"])
    assert body["userName"] == "alice@example.com"
    assert body["displayName"] == rest_user["name"]
    assert body["name"] == {"formatted": rest_user["name"]}
    assert body["active"] is True
    assert body["emails"] == [
        {
            "value": "alice@example.com",
            "type": "work",
            "primary": True,
        }
    ]
    assert body["meta"]["resourceType"] == "User"
    assert body["meta"]["location"].endswith(f"/scim/v2/Users/{rest_user['id']}")
    assert "lastModified" not in body["meta"]


def test_unknown_id_returns_scim_404() -> None:
    response = client.get(
        "/scim/v2/Users/999999",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 404
    assert_scim_media_type(response)
    assert response.json() == {
        "schemas": [SCIM_SCHEMA_ERROR],
        "detail": "User not found",
        "status": "404",
    }


def test_pagination_works() -> None:
    users = sorted(client.get("/users").json(), key=lambda user: user["id"])

    response = get_scim_users(
        {
            "sortBy": "id",
            "sortOrder": "ascending",
            "startIndex": "2",
            "count": "2",
        }
    )

    assert response.status_code == 200

    body = response.json()

    assert body["startIndex"] == 2
    assert body["itemsPerPage"] == 2
    assert [resource["id"] for resource in body["Resources"]] == [
        str(user["id"]) for user in users[1:3]
    ]


def test_count_is_respected() -> None:
    response = get_scim_users({"count": "1"})

    assert response.status_code == 200
    assert response.json()["itemsPerPage"] == 1
    assert len(response.json()["Resources"]) == 1


def test_start_index_is_respected() -> None:
    users = sorted(client.get("/users").json(), key=lambda user: user["id"])

    response = get_scim_users(
        {
            "sortBy": "id",
            "startIndex": "3",
            "count": "1",
        }
    )

    assert response.status_code == 200
    assert response.json()["Resources"][0]["id"] == str(users[2]["id"])


def test_out_of_range_pagination_is_empty() -> None:
    response = get_scim_users({"startIndex": "999999", "count": "10"})

    assert response.status_code == 200

    body = response.json()

    assert body["startIndex"] == 999999
    assert body["itemsPerPage"] == 0
    assert body["Resources"] == []


def test_username_eq_filter() -> None:
    response = get_scim_users({"filter": 'userName eq "alice@example.com"'})

    assert response.status_code == 200

    body = response.json()

    assert body["totalResults"] == 1
    assert body["Resources"][0]["userName"] == "alice@example.com"


def test_id_eq_filter() -> None:
    rest_user = find_rest_user("ian@example.com")

    response = get_scim_users({"filter": f'id eq "{rest_user["id"]}"'})

    assert response.status_code == 200

    body = response.json()

    assert body["totalResults"] == 1
    assert body["Resources"][0]["id"] == str(rest_user["id"])


def test_display_name_contains_filter() -> None:
    response = get_scim_users({"filter": 'displayName co "Alice"'})

    assert response.status_code == 200
    assert response.json()["totalResults"] >= 1
    assert all(
        "alice" in resource["displayName"].lower()
        for resource in response.json()["Resources"]
    )


def test_active_eq_true_filter() -> None:
    response = get_scim_users({"filter": "active eq true"})

    assert response.status_code == 200
    assert response.json()["totalResults"] >= 1
    assert all(resource["active"] is True for resource in response.json()["Resources"])


def test_active_eq_false_filter() -> None:
    inactive_user = create_user(name="Inactive SCIM User", active=False)

    response = get_scim_users({"filter": "active eq false", "count": "1000"})

    assert response.status_code == 200

    body = response.json()

    assert body["totalResults"] >= 1
    assert str(inactive_user["id"]) in {
        resource["id"] for resource in body["Resources"]
    }
    assert all(resource["active"] is False for resource in body["Resources"])


def test_malformed_filter_is_rejected() -> None:
    response = get_scim_users({"filter": "userName eq alice@example.com"})

    assert response.status_code == 400
    assert_scim_media_type(response)
    assert response.json()["schemas"] == [SCIM_SCHEMA_ERROR]
    assert response.json()["scimType"] == "invalidFilter"


def test_attributes_projection_works() -> None:
    response = get_scim_users(
        {
            "filter": 'userName eq "alice@example.com"',
            "attributes": "userName",
        }
    )

    assert response.status_code == 200

    resource = response.json()["Resources"][0]

    assert resource == {
        "schemas": [SCIM_SCHEMA_USER],
        "id": resource["id"],
        "userName": "alice@example.com",
    }


def test_excluded_attributes_projection_works() -> None:
    response = get_scim_users(
        {
            "filter": 'userName eq "alice@example.com"',
            "excludedAttributes": "meta",
        }
    )

    assert response.status_code == 200

    resource = response.json()["Resources"][0]

    assert "meta" not in resource
    assert resource["userName"] == "alice@example.com"


def test_sorting_ascending() -> None:
    response = get_scim_users(
        {
            "sortBy": "userName",
            "sortOrder": "ascending",
            "count": "5",
        }
    )

    assert response.status_code == 200

    user_names = [resource["userName"] for resource in response.json()["Resources"]]

    assert user_names == sorted(user_names, key=str.lower)


def test_sorting_descending() -> None:
    response = get_scim_users(
        {
            "sortBy": "displayName",
            "sortOrder": "descending",
            "count": "5",
        }
    )

    assert response.status_code == 200

    display_names = [
        resource["displayName"] for resource in response.json()["Resources"]
    ]

    assert display_names == sorted(display_names, key=str.lower, reverse=True)


def test_unsupported_sort_is_rejected() -> None:
    response = get_scim_users({"sortBy": "department"})

    assert response.status_code == 400
    assert_scim_media_type(response)
    assert response.json()["schemas"] == [SCIM_SCHEMA_ERROR]
    assert response.json()["scimType"] == "invalidPath"


def test_unauthorized_request_returns_scim_401() -> None:
    response = client.get("/scim/v2/Users")

    assert response.status_code == 401
    assert_scim_media_type(response)
    assert response.json() == {
        "schemas": [SCIM_SCHEMA_ERROR],
        "detail": "Authentication required",
        "status": "401",
    }


def test_helpdesk_receives_scim_403() -> None:
    response = client.get(
        "/scim/v2/Users",
        headers=auth_headers("sarah@example.com"),
    )

    assert response.status_code == 403
    assert_scim_media_type(response)
    assert response.json() == {
        "schemas": [SCIM_SCHEMA_ERROR],
        "detail": "Insufficient privileges",
        "status": "403",
    }


def test_employee_receives_scim_403() -> None:
    response = client.get(
        "/scim/v2/Users",
        headers=auth_headers("bob@example.com"),
    )

    assert response.status_code == 403
    assert_scim_media_type(response)
    assert response.json() == {
        "schemas": [SCIM_SCHEMA_ERROR],
        "detail": "Insufficient privileges",
        "status": "403",
    }


def test_iam_admin_succeeds() -> None:
    response = client.get(
        "/scim/v2/Users",
        headers=auth_headers("ian@example.com"),
    )

    assert response.status_code == 200


def test_security_admin_succeeds() -> None:
    response = client.get(
        "/scim/v2/Users",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 200


def test_openapi_documents_scim_user_query_parameters() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200

    operation = response.json()["paths"]["/scim/v2/Users"]["get"]
    parameters = {parameter["name"] for parameter in operation["parameters"]}

    assert operation["summary"] == "List SCIM users"
    assert operation["description"]
    assert {
        "startIndex",
        "count",
        "filter",
        "attributes",
        "excludedAttributes",
        "sortBy",
        "sortOrder",
    }.issubset(parameters)
    assert operation["security"] == [{"OAuth2PasswordBearer": []}]
