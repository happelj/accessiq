from pathlib import Path

from app.config import get_database_settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]
K6_ROOT = PROJECT_ROOT / "performance" / "k6"


EXPECTED_K6_SCRIPTS = {
    "auth.js",
    "users.js",
    "applications.js",
    "scim.js",
    "graph.js",
    "ai.js",
    "reviews.js",
    "provisioning.js",
    "health.js",
    "full-system.js",
}


def test_k6_performance_scripts_are_present() -> None:
    scripts = {path.name for path in K6_ROOT.glob("*.js")}

    assert EXPECTED_K6_SCRIPTS <= scripts
    assert (K6_ROOT / "lib" / "config.js").is_file()
    assert (K6_ROOT / "lib" / "auth.js").is_file()


def test_k6_scripts_export_options_and_default_function() -> None:
    for script_name in EXPECTED_K6_SCRIPTS:
        script = K6_ROOT / script_name
        contents = script.read_text(encoding="utf-8")

        assert "export const options" in contents
        assert "export default function" in contents


def test_k6_scripts_avoid_destructive_http_methods() -> None:
    destructive_patterns = ("http.put(", "http.patch(", "http.del(", "http.delete(")

    for script_name in EXPECTED_K6_SCRIPTS:
        contents = (K6_ROOT / script_name).read_text(encoding="utf-8")

        for pattern in destructive_patterns:
            assert pattern not in contents


def test_database_pool_settings_are_configurable(monkeypatch) -> None:
    get_database_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@db/app")
    monkeypatch.setenv("DATABASE_POOL_PRE_PING", "false")
    monkeypatch.setenv("DATABASE_POOL_SIZE", "12")
    monkeypatch.setenv("DATABASE_MAX_OVERFLOW", "24")
    monkeypatch.setenv("DATABASE_POOL_TIMEOUT", "45")
    monkeypatch.setenv("DATABASE_POOL_RECYCLE_SECONDS", "900")

    settings = get_database_settings()

    assert settings.database_backend == "postgresql"
    assert settings.pool_pre_ping is False
    assert settings.pool_size == 12
    assert settings.max_overflow == 24
    assert settings.pool_timeout == 45
    assert settings.pool_recycle_seconds == 900
    get_database_settings.cache_clear()
