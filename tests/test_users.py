from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "healthy"
    assert body["correlation_id"] == response.headers["X-Correlation-ID"]
    assert set(body["subsystems"]) == {
        "database",
        "connectors",
        "audit",
        "provisioning",
        "domain_events",
        "configuration",
    }
    assert body["subsystems"]["database"]["status"] == "healthy"
    assert isinstance(body["metrics"], dict)


def test_health_check_accepts_supplied_correlation_id() -> None:
    correlation_id = f"health-{uuid4()}"

    response = client.get(
        "/health",
        headers={"X-Correlation-ID": correlation_id},
    )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == correlation_id
    assert response.json()["correlation_id"] == correlation_id


def test_list_users() -> None:
    response = client.get("/users")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_existing_user() -> None:
    response = client.get("/users/1")

    assert response.status_code == 200
    assert response.json()["id"] == 1


def test_get_missing_user() -> None:
    response = client.get("/users/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


def test_create_user() -> None:
    unique_email = f"test-{uuid4()}@example.com"

    response = client.post(
        "/users",
        json={
            "name": "Test User",
            "email": unique_email,
            "department": "Engineering",
            "active": True,
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["name"] == "Test User"
    assert body["email"] == unique_email
    assert body["department"] == "Engineering"
    assert body["active"] is True
    assert isinstance(body["id"], int)


def test_duplicate_email_is_rejected() -> None:
    unique_email = f"duplicate-{uuid4()}@example.com"

    payload = {
        "name": "First User",
        "email": unique_email,
        "department": "Sales",
        "active": True,
    }

    first_response = client.post("/users", json=payload)
    second_response = client.post("/users", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {
        "detail": "A user with this email already exists"
    }
