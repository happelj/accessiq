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


@dataclass(frozen=True)
class AuthSettings:
    jwt_secret: str
    jwt_algorithm: str
    access_token_expire_minutes: int


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
