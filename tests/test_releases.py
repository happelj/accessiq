from fastapi.testclient import TestClient

from app.config import ReleaseSettings
from app.database import SessionLocal
from app.main import app
from app.releases.services import ReleaseService


client = TestClient(app)


def auth_headers(email: str = "alice@example.com") -> dict[str, str]:
    response = client.post(
        "/login",
        json={"email": email, "password": "Password123!"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_version_endpoint_returns_release_metadata() -> None:
    response = client.get("/version")

    assert response.status_code == 200
    body = response.json()

    assert body["service"] == "AccessIQ"
    assert body["environment"] == "local"
    assert body["git_sha"] == "unknown"
    assert body["helm_chart_version"] == "0.1.0"
    assert "version" in body
    assert "docker_image" in body
    assert "image_digest" in body
    assert "terraform_version" in body


def test_release_history_requires_authentication_and_rbac() -> None:
    unauthenticated_response = client.get("/releases")
    employee_response = client.get(
        "/releases",
        headers=auth_headers("bob@example.com"),
    )
    auditor_response = client.get(
        "/releases",
        headers=auth_headers("auditor@example.com"),
    )

    assert unauthenticated_response.status_code == 401
    assert employee_response.status_code == 403
    assert auditor_response.status_code == 200


def test_current_release_returns_metadata_and_deployment() -> None:
    response = client.get("/releases/current", headers=auth_headers())

    assert response.status_code == 200
    body = response.json()

    assert body["metadata"]["service"] == "AccessIQ"
    assert body["metadata"]["environment"] == "local"
    assert body["deployment"] is not None
    assert body["deployment"]["environment"] == "local"
    assert body["deployment"]["status"] == "deployed"


def test_release_service_records_current_deployment_idempotently() -> None:
    settings = ReleaseSettings(
        release_version="test-release",
        environment="test",
        git_sha="abc123def456",
        git_tag="v-test",
        build_timestamp="2026-07-16T12:00:00Z",
        docker_image="example.test/accessiq-api:test-release",
        image_digest="sha256:testdigest",
        helm_chart_version="0.1.0",
        helm_revision="7",
        terraform_version=">= 1.10.0, < 2.0.0",
        deployment_operator="pytest",
        deployment_status="deployed",
        deployed_at="2026-07-16T12:01:00Z",
    )

    with SessionLocal() as db:
        service = ReleaseService(db, settings=settings)
        first = service.record_current_deployment()
        db.commit()
        first_id = first.id

        second = service.record_current_deployment()
        db.commit()

        assert second.id == first_id
        current = service.current_deployment()

    assert current is not None
    assert current.id == first_id
    assert current.git_tag == "v-test"
    assert current.image_digest == "sha256:testdigest"


def test_release_openapi_metadata() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/version" in paths
    assert "/releases" in paths
    assert "/releases/current" in paths
    assert paths["/version"]["get"]["tags"] == ["Releases"]
