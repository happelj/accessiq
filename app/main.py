from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from .database import Base, SessionLocal, engine, get_db
from .models import AccessAssignment, Application, Entitlement, User
from .schemas import (
    AccessGrantRequest,
    AccessResponse,
    ApplicationResponse,
    EntitlementResponse,
    HealthResponse,
    UserCreate,
    UserResponse,
)

SEEDED_APPLICATIONS = [
    {"name": "Salesforce", "slug": "salesforce"},
    {"name": "Zendesk", "slug": "zendesk"},
    {"name": "Finance Portal", "slug": "finance-portal"},
    {"name": "GitHub", "slug": "github"},
]

SEEDED_ENTITLEMENTS = [
    {
        "application_slug": "salesforce",
        "name": "Salesforce User",
        "slug": "user",
    },
    {
        "application_slug": "salesforce",
        "name": "Salesforce Administrator",
        "slug": "administrator",
    },
    {
        "application_slug": "zendesk",
        "name": "Zendesk Agent",
        "slug": "agent",
    },
    {
        "application_slug": "zendesk",
        "name": "Zendesk Administrator",
        "slug": "administrator",
    },
    {
        "application_slug": "finance-portal",
        "name": "Finance Read Only",
        "slug": "read-only",
    },
    {
        "application_slug": "finance-portal",
        "name": "Finance Administrator",
        "slug": "administrator",
    },
    {
        "application_slug": "github",
        "name": "GitHub Developer",
        "slug": "developer",
    },
    {
        "application_slug": "github",
        "name": "GitHub Administrator",
        "slug": "administrator",
    },
]


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


def seed_applications_and_entitlements() -> None:
    """Insert reference application data without duplicating existing rows."""
    with SessionLocal() as db:
        applications_by_slug = {
            application.slug: application
            for application in db.scalars(select(Application)).all()
        }

        for application_data in SEEDED_APPLICATIONS:
            application = applications_by_slug.get(application_data["slug"])

            if application is not None:
                continue

            application = Application(**application_data)
            db.add(application)
            applications_by_slug[application.slug] = application

        db.flush()

        entitlements = db.scalars(select(Entitlement)).all()
        entitlement_keys = {
            (entitlement.application_id, entitlement.slug)
            for entitlement in entitlements
        }

        for entitlement_data in SEEDED_ENTITLEMENTS:
            application = applications_by_slug[entitlement_data["application_slug"]]
            entitlement_key = (application.id, entitlement_data["slug"])

            if entitlement_key in entitlement_keys:
                continue

            db.add(
                Entitlement(
                    name=entitlement_data["name"],
                    slug=entitlement_data["slug"],
                    application_id=application.id,
                )
            )
            entitlement_keys.add(entitlement_key)

        db.commit()


def access_assignment_to_response(
    assignment: AccessAssignment,
) -> AccessResponse:
    entitlement = assignment.entitlement
    application = entitlement.application

    return AccessResponse(
        id=assignment.id,
        user_id=assignment.user_id,
        application_id=application.id,
        application=application.name,
        entitlement_id=entitlement.id,
        entitlement=entitlement.name,
        status="active",
        granted_at=assignment.granted_at,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    seed_users()
    seed_applications_and_entitlements()
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


@app.get("/applications", response_model=list[ApplicationResponse])
def list_applications(db: Session = Depends(get_db)) -> list[Application]:
    applications = db.scalars(select(Application).order_by(Application.id)).all()
    return list(applications)


@app.get(
    "/applications/{application_id}/entitlements",
    response_model=list[EntitlementResponse],
)
def list_application_entitlements(
    application_id: int,
    db: Session = Depends(get_db),
) -> list[Entitlement]:
    application = db.get(Application, application_id)

    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    entitlements = db.scalars(
        select(Entitlement)
        .where(Entitlement.application_id == application_id)
        .order_by(Entitlement.id)
    ).all()

    return list(entitlements)


@app.get("/users/{user_id}/access", response_model=list[AccessResponse])
def list_user_access(
    user_id: int,
    db: Session = Depends(get_db),
) -> list[AccessResponse]:
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    assignments = db.scalars(
        select(AccessAssignment)
        .options(
            joinedload(AccessAssignment.entitlement).joinedload(
                Entitlement.application
            )
        )
        .where(AccessAssignment.user_id == user_id)
        .order_by(AccessAssignment.id)
    ).all()

    return [access_assignment_to_response(assignment) for assignment in assignments]


@app.post(
    "/access/grant",
    response_model=AccessResponse,
    status_code=status.HTTP_201_CREATED,
)
def grant_access(
    access_data: AccessGrantRequest,
    db: Session = Depends(get_db),
) -> AccessResponse:
    user = db.get(User, access_data.user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    entitlement = db.scalar(
        select(Entitlement)
        .options(joinedload(Entitlement.application))
        .where(Entitlement.id == access_data.entitlement_id)
    )

    if entitlement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entitlement not found",
        )

    existing_assignment = db.scalar(
        select(AccessAssignment).where(
            AccessAssignment.user_id == access_data.user_id,
            AccessAssignment.entitlement_id == access_data.entitlement_id,
        )
    )

    if existing_assignment is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already has this access",
        )

    assignment = AccessAssignment(
        user_id=access_data.user_id,
        entitlement_id=access_data.entitlement_id,
    )

    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    assignment = db.scalar(
        select(AccessAssignment)
        .options(
            joinedload(AccessAssignment.entitlement).joinedload(
                Entitlement.application
            )
        )
        .where(AccessAssignment.id == assignment.id)
    )

    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Access assignment not found",
        )

    return access_assignment_to_response(assignment)


@app.post("/access/revoke")
def revoke_access(
    access_data: AccessGrantRequest,
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    user = db.get(User, access_data.user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    entitlement = db.get(Entitlement, access_data.entitlement_id)

    if entitlement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entitlement not found",
        )

    assignment = db.scalar(
        select(AccessAssignment).where(
            AccessAssignment.user_id == access_data.user_id,
            AccessAssignment.entitlement_id == access_data.entitlement_id,
        )
    )

    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Access assignment not found",
        )

    db.delete(assignment)
    db.commit()

    return {
        "status": "revoked",
        "user_id": access_data.user_id,
        "entitlement_id": access_data.entitlement_id,
    }
