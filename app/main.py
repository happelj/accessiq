from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .auth import create_access_token, hash_password, verify_password
from .config import get_auth_settings
from .database import Base, SessionLocal, engine, get_db
from .models import User
from .schemas import HealthResponse, LoginRequest, TokenResponse, UserResponse

SEED_USER_PASSWORD = "Password123!"
SEEDED_USERS = [
    {
        "name": "Bob Smith",
        "email": "bob@example.com",
        "department": "Sales",
        "active": True,
    },
    {
        "name": "Sarah Chen",
        "email": "sarah@example.com",
        "department": "Finance",
        "active": True,
    },
    {
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "department": "Engineering",
        "active": True,
    },
]


def ensure_schema_compatibility() -> None:
    """Apply idempotent compatibility updates for pre-migration schemas."""
    inspector = inspect(engine)
    user_columns = {column["name"] for column in inspector.get_columns("users")}

    if "password_hash" in user_columns:
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN password_hash VARCHAR(255) NOT NULL DEFAULT ''"
            )
        )


def seed_users() -> None:
    """Insert or update seed users without storing plaintext passwords."""
    with SessionLocal() as db:
        for user_data in SEEDED_USERS:
            user = db.scalar(select(User).where(User.email == user_data["email"]))

            if user is None:
                db.add(
                    User(
                        **user_data,
                        password_hash=hash_password(SEED_USER_PASSWORD),
                    )
                )
                continue

            user.name = user_data["name"]
            user.department = user_data["department"]
            user.active = user_data["active"]

            if not verify_password(SEED_USER_PASSWORD, user.password_hash):
                user.password_hash = hash_password(SEED_USER_PASSWORD)

        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    seed_users()
    yield


app = FastAPI(
    title="AccessIQ",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/")
def read_root() -> dict[str, str]:
    return {
        "service": "AccessIQ",
        "documentation": "/docs",
    }


@app.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
)
def health_check(db: Session = Depends(get_db)) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed",
        ) from exc

    return HealthResponse(status="healthy")


@app.post("/login", response_model=TokenResponse)
def login(
    credentials: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = db.scalar(
        select(User).where(User.email == credentials.email.lower())
    )

    if user is None or not verify_password(
        credentials.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_auth_settings()
    access_token = create_access_token(subject=str(user.id))

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )


@app.get("/users", response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db)) -> list[User]:
    users = db.scalars(select(User).order_by(User.id)).all()
    return list(users)
