from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import get_auth_settings
from .database import get_db
from .models import User
from .request_context import set_authenticated_user

password_context = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login", auto_error=False)


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False

    try:
        return password_context.verify(password, password_hash)
    except Exception:
        return False


def create_access_token(subject: str) -> str:
    settings = get_auth_settings()
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(
        minutes=settings.access_token_expire_minutes,
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }

    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_auth_settings()

    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )


def unauthorized_exception(detail: str = "Authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if token is None:
        raise unauthorized_exception()

    try:
        payload = decode_access_token(token)
    except ExpiredSignatureError as exc:
        raise unauthorized_exception() from exc
    except JWTError as exc:
        raise unauthorized_exception() from exc

    subject = payload.get("sub")

    if subject is None:
        raise unauthorized_exception()

    try:
        user_id = int(subject)
    except ValueError as exc:
        raise unauthorized_exception() from exc

    user = db.get(User, user_id)

    if user is None:
        raise unauthorized_exception()

    set_authenticated_user(user)

    return user
