from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.scim.constants import (
    SCIM_MEDIA_TYPE,
    SCIM_SCHEMA_ENTERPRISE_USER,
    SCIM_SCHEMA_ERROR,
    SCIM_SCHEMA_GROUP,
    SCIM_SCHEMA_LIST_RESPONSE,
    SCIM_SCHEMA_RESOURCE_TYPE,
    SCIM_SCHEMA_SCHEMA,
    SCIM_SCHEMA_SERVICE_PROVIDER_CONFIG,
    SCIM_SCHEMA_USER,
)
from app.scim.pagination import ScimListResponse


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


@pytest.mark.parametrize(
    "path",
    [
        "/scim/v2/ServiceProviderConfig",
        "/scim/v2/ResourceTypes",
        "/scim/v2/Schemas",
    ],
)
def test_scim_endpoints_require_authentication(path: str) -> None:
    response = client.get(path)

    assert response.status_code == 401
    assert_scim_media_type(response)
    assert response.json() == {
        "schemas": [SCIM_SCHEMA_ERROR],
        "detail": "Authentication required",
        "status": "401",
    }


@pytest.mark.parametrize(
    "email",
    [
        "sarah@example.com",
        "bob@example.com",
    ],
)
def test_non_admin_roles_cannot_access_scim(email: str) -> None:
    response = client.get(
        "/scim/v2/ServiceProviderConfig",
        headers=auth_headers(email),
    )

    assert response.status_code == 403
    assert_scim_media_type(response)
    assert response.json() == {
        "schemas": [SCIM_SCHEMA_ERROR],
        "detail": "Insufficient privileges",
        "status": "403",
    }


@pytest.mark.parametrize(
    "email",
    [
        "alice@example.com",
        "ian@example.com",
    ],
)
def test_admin_roles_can_access_scim(email: str) -> None:
    response = client.get(
        "/scim/v2/ServiceProviderConfig",
        headers=auth_headers(email),
    )

    assert response.status_code == 200
    assert_scim_media_type(response)
    assert response.json()["schemas"] == [SCIM_SCHEMA_SERVICE_PROVIDER_CONFIG]


def test_service_provider_config_returns_supported_capabilities() -> None:
    response = client.get(
        "/scim/v2/ServiceProviderConfig",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 200
    assert_scim_media_type(response)

    body = response.json()

    assert body["schemas"] == [SCIM_SCHEMA_SERVICE_PROVIDER_CONFIG]
    assert body["patch"] == {"supported": False}
    assert body["bulk"] == {
        "supported": False,
        "maxOperations": 0,
        "maxPayloadSize": 0,
    }
    assert body["filter"] == {"supported": True, "maxResults": 100}
    assert body["changePassword"] == {"supported": False}
    assert body["sort"] == {"supported": True}
    assert body["etag"] == {"supported": False}
    assert body["xmlDataFormat"] == {"supported": False}
    assert body["authenticationSchemes"][0]["type"] == "oauthbearertoken"
    assert body["authenticationSchemes"][0]["primary"] is True


def test_resource_types_returns_user_and_group_metadata() -> None:
    response = client.get(
        "/scim/v2/ResourceTypes",
        headers=auth_headers("alice@example.com"),
    )

    assert response.status_code == 200
    assert_scim_media_type(response)

    body = response.json()
    resources = {resource["id"]: resource for resource in body["Resources"]}

    assert body["schemas"] == [SCIM_SCHEMA_LIST_RESPONSE]
    assert body["totalResults"] == 2
    assert body["startIndex"] == 1
    assert body["itemsPerPage"] == 2
    assert set(resources) == {"User", "Group"}
    assert resources["User"]["schemas"] == [SCIM_SCHEMA_RESOURCE_TYPE]
    assert resources["User"]["schema"] == SCIM_SCHEMA_USER
    assert resources["User"]["endpoint"] == "/Users"
    assert resources["User"]["schemaExtensions"] == [
        {"schema": SCIM_SCHEMA_ENTERPRISE_USER, "required": False}
    ]
    assert resources["Group"]["schema"] == SCIM_SCHEMA_GROUP
    assert resources["Group"]["endpoint"] == "/Groups"


def test_schemas_returns_user_group_and_enterprise_metadata() -> None:
    response = client.get(
        "/scim/v2/Schemas",
        headers=auth_headers("ian@example.com"),
    )

    assert response.status_code == 200
    assert_scim_media_type(response)

    body = response.json()
    resources = {resource["id"]: resource for resource in body["Resources"]}

    assert body["schemas"] == [SCIM_SCHEMA_LIST_RESPONSE]
    assert body["totalResults"] == 3
    assert body["itemsPerPage"] == 3
    assert {
        SCIM_SCHEMA_USER,
        SCIM_SCHEMA_GROUP,
        SCIM_SCHEMA_ENTERPRISE_USER,
    } == set(resources)
    assert resources[SCIM_SCHEMA_USER]["schemas"] == [SCIM_SCHEMA_SCHEMA]
    assert resources[SCIM_SCHEMA_USER]["name"] == "User"
    assert any(
        attribute["name"] == "userName" and attribute["required"] is True
        for attribute in resources[SCIM_SCHEMA_USER]["attributes"]
    )
    assert resources[SCIM_SCHEMA_GROUP]["name"] == "Group"
    assert resources[SCIM_SCHEMA_ENTERPRISE_USER]["name"] == "EnterpriseUser"


def test_scim_pagination_model_serializes_common_fields() -> None:
    response = ScimListResponse(
        totalResults=1,
        startIndex=1,
        itemsPerPage=1,
        Resources=[{"id": "example"}],
    )

    assert response.model_dump() == {
        "schemas": [SCIM_SCHEMA_LIST_RESPONSE],
        "totalResults": 1,
        "startIndex": 1,
        "itemsPerPage": 1,
        "Resources": [{"id": "example"}],
    }


def test_scim_openapi_metadata_is_grouped_and_secured() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200

    schema = response.json()

    for path in [
        "/scim/v2/ServiceProviderConfig",
        "/scim/v2/ResourceTypes",
        "/scim/v2/Schemas",
    ]:
        operation = schema["paths"][path]["get"]

        assert operation["tags"] == ["SCIM"]
        assert operation["summary"]
        assert operation["description"]
        assert operation["security"] == [{"OAuth2PasswordBearer": []}]
