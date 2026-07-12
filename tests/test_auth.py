from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from jose import jwt

from app.auth import get_current_user, hash_password, verify_password
from app.config import get_auth_settings
from app.main import app
from app.models import User


@app.get("/__tests/current-user")
def read_current_user(
    current_user: User = Depends(get_current_user),
) -> dict[str, int | str]:
    return {
        "id": current_user.id,
        "email": current_user.email,
    }


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def get_seed_user(client: TestClient, email: str) -> dict[str, object]:
    response = client.get("/users")

    assert response.status_code == 200

    for user in response.json():
        if user["email"] == email:
            return user

    raise AssertionError(f"Seed user {email!r} was not found")


def login(client: TestClient, email: str, password: str) -> dict[str, object]:
    response = client.post(
        "/login",
        json={
            "email": email,
            "password": password,
        },
    )

    assert response.status_code == 200

    return response.json()


def test_password_hashing_uses_argon2() -> None:
    password_hash = hash_password("Password123!")

    assert password_hash != "Password123!"
    assert password_hash.startswith("$argon2")


def test_verify_password_succeeds() -> None:
    password_hash = hash_password("Password123!")

    assert verify_password("Password123!", password_hash) is True


def test_verify_password_fails() -> None:
    password_hash = hash_password("Password123!")

    assert verify_password("WrongPassword123!", password_hash) is False


def test_successful_login(client: TestClient) -> None:
    body = login(client, "alice@example.com", "Password123!")

    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)
    assert body["expires_in"] == 1800


def test_unknown_user_login_returns_401(client: TestClient) -> None:
    response = client.post(
        "/login",
        json={
            "email": "missing@example.com",
            "password": "Password123!",
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}


def test_wrong_password_login_returns_401(client: TestClient) -> None:
    response = client.post(
        "/login",
        json={
            "email": "alice@example.com",
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}


def test_jwt_contains_expected_subject(client: TestClient) -> None:
    user = get_seed_user(client, "alice@example.com")
    body = login(client, "alice@example.com", "Password123!")
    settings = get_auth_settings()
    payload = jwt.decode(
        body["access_token"],
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )

    assert payload["sub"] == str(user["id"])


def test_jwt_expiration_exists(client: TestClient) -> None:
    body = login(client, "alice@example.com", "Password123!")
    settings = get_auth_settings()
    payload = jwt.decode(
        body["access_token"],
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )

    assert "iat" in payload
    assert "exp" in payload
    assert payload["exp"] > payload["iat"]


def test_get_current_user_succeeds(client: TestClient) -> None:
    user = get_seed_user(client, "alice@example.com")
    body = login(client, "alice@example.com", "Password123!")
    response = client.get(
        "/__tests/current-user",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": user["id"],
        "email": "alice@example.com",
    }


def test_expired_token_rejected(client: TestClient) -> None:
    user = get_seed_user(client, "alice@example.com")
    settings = get_auth_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(user["id"]),
            "iat": int((now - timedelta(minutes=10)).timestamp()),
            "exp": int((now - timedelta(minutes=5)).timestamp()),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    response = client.get(
        "/__tests/current-user",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_tampered_token_rejected(client: TestClient) -> None:
    body = login(client, "alice@example.com", "Password123!")
    token = body["access_token"]
    header, payload, signature = token.split(".")
    tampered_signature = ("a" if signature[0] != "a" else "b") + signature[1:]
    tampered_token = ".".join([header, payload, tampered_signature])

    response = client.get(
        "/__tests/current-user",
        headers={"Authorization": f"Bearer {tampered_token}"},
    )

    assert response.status_code == 401


def test_missing_bearer_token_rejected(client: TestClient) -> None:
    response = client.get("/__tests/current-user")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
