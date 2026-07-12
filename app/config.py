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


@lru_cache
def get_auth_settings() -> AuthSettings:
    return AuthSettings(
        jwt_secret=os.getenv("JWT_SECRET", "dev-accessiq-change-me"),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        access_token_expire_minutes=_get_int_env(
            "ACCESS_TOKEN_EXPIRE_MINUTES",
            30,
        ),
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
