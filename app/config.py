import os
from dataclasses import dataclass
from functools import lru_cache


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)

    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AuthSettings:
    jwt_secret: str
    jwt_algorithm: str
    access_token_expire_minutes: int


@dataclass(frozen=True)
class ConnectorSettings:
    enable_salesforce_connector: bool
    enable_github_connector: bool
    enable_zendesk_connector: bool
    enable_finance_connector: bool
    salesforce_api_base_url: str | None
    github_api_base_url: str | None
    zendesk_api_base_url: str | None
    finance_api_base_url: str | None


@dataclass(frozen=True)
class DatabaseSettings:
    database_url: str
    database_backend: str


@dataclass(frozen=True)
class LoggingSettings:
    logger_name: str
    log_level: str


@dataclass(frozen=True)
class ReleaseSettings:
    release_version: str
    environment: str
    git_sha: str
    git_tag: str | None
    build_timestamp: str | None
    docker_image: str | None
    image_digest: str | None
    helm_chart_version: str
    helm_revision: str | None
    terraform_version: str | None
    deployment_operator: str
    deployment_status: str
    deployed_at: str | None


@dataclass(frozen=True)
class CorsSettings:
    allowed_origins: list[str]
    allow_credentials: bool


@lru_cache
def get_auth_settings() -> AuthSettings:
    return AuthSettings(
        jwt_secret=os.getenv("JWT_SECRET", "dev-accessiq-change-me-minimum-32-bytes"),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        access_token_expire_minutes=_get_int_env(
            "ACCESS_TOKEN_EXPIRE_MINUTES",
            30,
        ),
    )


@lru_cache
def get_database_settings() -> DatabaseSettings:
    database_url = os.getenv("DATABASE_URL", "sqlite:///./accessiq.db")
    return DatabaseSettings(
        database_url=database_url,
        database_backend=_database_backend(database_url),
    )


@lru_cache
def get_connector_settings() -> ConnectorSettings:
    return ConnectorSettings(
        enable_salesforce_connector=_get_bool_env(
            "ENABLE_SALESFORCE_CONNECTOR",
            True,
        ),
        enable_github_connector=_get_bool_env("ENABLE_GITHUB_CONNECTOR", True),
        enable_zendesk_connector=_get_bool_env("ENABLE_ZENDESK_CONNECTOR", True),
        enable_finance_connector=_get_bool_env("ENABLE_FINANCE_CONNECTOR", True),
        salesforce_api_base_url=os.getenv("SALESFORCE_API_BASE_URL"),
        github_api_base_url=os.getenv("GITHUB_API_BASE_URL"),
        zendesk_api_base_url=os.getenv("ZENDESK_API_BASE_URL"),
        finance_api_base_url=os.getenv("FINANCE_API_BASE_URL"),
    )


@lru_cache
def get_logging_settings() -> LoggingSettings:
    return LoggingSettings(
        logger_name=os.getenv("ACCESSIQ_LOGGER_NAME", "accessiq"),
        log_level=os.getenv("ACCESSIQ_LOG_LEVEL", "INFO").upper(),
    )


@lru_cache
def get_release_settings() -> ReleaseSettings:
    git_sha = os.getenv("ACCESSIQ_GIT_SHA", "unknown")
    git_tag = _empty_to_none(os.getenv("ACCESSIQ_GIT_TAG"))
    release_version = os.getenv("ACCESSIQ_VERSION")

    if release_version is None:
        release_version = git_tag or _short_sha(git_sha) or "0.1.0"

    return ReleaseSettings(
        release_version=release_version,
        environment=os.getenv("ACCESSIQ_ENVIRONMENT", "local"),
        git_sha=git_sha,
        git_tag=git_tag,
        build_timestamp=_empty_to_none(os.getenv("ACCESSIQ_BUILD_TIMESTAMP")),
        docker_image=_empty_to_none(os.getenv("ACCESSIQ_DOCKER_IMAGE")),
        image_digest=_empty_to_none(os.getenv("ACCESSIQ_IMAGE_DIGEST")),
        helm_chart_version=os.getenv("ACCESSIQ_HELM_CHART_VERSION", "0.1.0"),
        helm_revision=_empty_to_none(os.getenv("ACCESSIQ_HELM_REVISION")),
        terraform_version=_empty_to_none(os.getenv("ACCESSIQ_TERRAFORM_VERSION")),
        deployment_operator=os.getenv("ACCESSIQ_DEPLOYMENT_OPERATOR", "unknown"),
        deployment_status=os.getenv("ACCESSIQ_DEPLOYMENT_STATUS", "deployed"),
        deployed_at=_empty_to_none(os.getenv("ACCESSIQ_DEPLOYED_AT")),
    )


@lru_cache
def get_cors_settings() -> CorsSettings:
    origins = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return CorsSettings(
        allowed_origins=[
            origin.strip() for origin in origins.split(",") if origin.strip()
        ],
        allow_credentials=_get_bool_env("CORS_ALLOW_CREDENTIALS", True),
    )


def _database_backend(database_url: str) -> str:
    if database_url.startswith("sqlite"):
        return "sqlite"
    if database_url.startswith("postgresql"):
        return "postgresql"

    return "unknown"


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None

    stripped = value.strip()
    return stripped or None


def _short_sha(git_sha: str) -> str | None:
    if not git_sha or git_sha == "unknown":
        return None

    return git_sha[:12]
