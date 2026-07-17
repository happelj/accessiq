from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_api_responses_include_security_headers() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert (
        response.headers["strict-transport-security"]
        == "max-age=31536000; includeSubDomains"
    )
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "camera=()" in response.headers["permissions-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_frontend_nginx_config_sets_security_headers() -> None:
    nginx_config = (REPO_ROOT / "frontend" / "nginx.conf").read_text()

    assert "add_header Content-Security-Policy" in nginx_config
    assert "add_header Strict-Transport-Security" in nginx_config
    assert "add_header Referrer-Policy" in nginx_config
    assert "add_header Permissions-Policy" in nginx_config
    assert "add_header X-Content-Type-Options" in nginx_config
    assert "add_header X-Frame-Options" in nginx_config


def test_security_supply_chain_scripts_are_documented() -> None:
    expected_paths = [
        "scripts/generate-sbom.sh",
        "scripts/container-scan.sh",
        "scripts/secret-scan.sh",
        "docs/security.md",
        "docs/threat-model.md",
        ".gitleaks.toml",
    ]

    for path in expected_paths:
        assert (REPO_ROOT / path).exists(), path


def test_ci_runs_security_supply_chain_checks() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "Generate application SBOMs" in workflow
    assert "Container vulnerability scan" in workflow
    assert "Secret scan" in workflow
    assert "Dependency review" in workflow
