from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine, get_db
from .models import User
from .schemas import HealthResponse, UserCreate, UserResponse


def seed_users() -> None:
    """Insert initial users only when the users table is empty."""
    with SessionLocal() as db:
        existing_user = db.scalar(select(User).limit(1))

        if existing_user is not None:
            return

        db.add_all(
            [
                User(
                    name="Bob Smith",
                    email="bob@example.com",
                    department="Sales",
                    active=True,
                ),
                User(
                    name="Sarah Chen",
                    email="sarah@example.com",
                    department="Finance",
                    active=True,
                ),
                User(
                    name="Alice Johnson",
                    email="alice@example.com",
                    department="Engineering",
                    active=True,
                ),
            ]
        )
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
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


@app.get("/users", response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db)) -> list[User]:
    users = db.scalars(select(User).order_by(User.id)).all()
    return list(users)


@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user


@app.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
) -> User:
    normalized_email = str(user_data.email).lower()

    existing_user = db.scalar(
        select(User).where(User.email == normalized_email)
    )

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    user = User(
        name=user_data.name,
        email=normalized_email,
        department=user_data.department,
        active=user_data.active,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user
