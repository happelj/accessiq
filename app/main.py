from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from .audit_service import create_audit_event
from .database import Base, SessionLocal, engine, get_db
from .models import AccessAssignment, Application, AuditEvent, Entitlement, User
from .policy_engine import evaluate_grant_policy, evaluate_revoke_policy
from .schemas import (
    AccessActionRequest,
    AccessResponse,
    AuditEventResponse,
    ApplicationResponse,
    AuditAction,
    AuditResult,
    EntitlementResponse,
    HealthResponse,
    UserCreate,
    UserResponse,
)

SEEDED_USERS = [
    {
        "name": "Bob Smith",
        "email": "bob@example.com",
        "department": "Sales",
        "active": True,
        "operator_role": "employee",
    },
    {
        "name": "Sarah Chen",
        "email": "sarah@example.com",
        "department": "Finance",
        "active": True,
        "operator_role": "help_desk",
    },
    {
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "department": "Engineering",
        "active": True,
        "operator_role": "administrator",
    },
    {
        "name": "Audit Reviewer",
        "email": "auditor@example.com",
        "department": "Compliance",
        "active": True,
        "operator_role": "auditor",
    },
]

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


def ensure_schema_compatibility() -> None:
    """Apply idempotent compatibility updates for pre-migration schemas."""
    inspector = inspect(engine)
    user_columns = {column["name"] for column in inspector.get_columns("users")}

    if "operator_role" in user_columns:
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN operator_role VARCHAR(50) NOT NULL DEFAULT 'employee'"
            )
        )


def seed_users() -> None:
    """Insert or update known seed users without duplicating rows."""
    with SessionLocal() as db:
        for user_data in SEEDED_USERS:
            user = db.scalar(select(User).where(User.email == user_data["email"]))

            if user is None:
                db.add(User(**user_data))
                continue

            user.name = user_data["name"]
            user.department = user_data["department"]
            user.active = user_data["active"]
            user.operator_role = user_data["operator_role"]

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


def audit_event_to_response(event: AuditEvent) -> AuditEventResponse:
    return AuditEventResponse(
        id=event.id,
        requester_id=event.requester_id,
        target_user_id=event.target_user_id,
        action=event.action,
        application_id=event.application_id,
        application=event.application.name,
        entitlement_id=event.entitlement_id,
        entitlement=event.entitlement.name,
        result=event.result,
        reason=event.reason,
        created_at=event.created_at,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
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
        operator_role=user_data.operator_role,
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
    access_data: AccessActionRequest,
    db: Session = Depends(get_db),
) -> AccessResponse:
    requester = db.get(User, access_data.requester_id)

    if requester is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requester not found",
        )

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

    application_id = entitlement.application.id

    existing_assignment = db.scalar(
        select(AccessAssignment).where(
            AccessAssignment.user_id == access_data.user_id,
            AccessAssignment.entitlement_id == access_data.entitlement_id,
        )
    )

    if existing_assignment is not None:
        try:
            create_audit_event(
                db,
                requester_id=access_data.requester_id,
                target_user_id=access_data.user_id,
                action="grant",
                application_id=application_id,
                entitlement_id=access_data.entitlement_id,
                result="denied",
                reason="User already has this access",
            )
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database operation failed",
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already has this access",
        )

    policy_decision = evaluate_grant_policy(requester, user, entitlement)

    if not policy_decision.allowed:
        try:
            create_audit_event(
                db,
                requester_id=access_data.requester_id,
                target_user_id=access_data.user_id,
                action="grant",
                application_id=application_id,
                entitlement_id=access_data.entitlement_id,
                result="denied",
                reason=policy_decision.reason,
            )
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database operation failed",
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=policy_decision.reason,
        )

    assignment = AccessAssignment(
        user_id=access_data.user_id,
        entitlement_id=access_data.entitlement_id,
    )

    try:
        db.add(assignment)
        db.flush()
        assignment_id = assignment.id
        create_audit_event(
            db,
            requester_id=access_data.requester_id,
            target_user_id=access_data.user_id,
            action="grant",
            application_id=application_id,
            entitlement_id=access_data.entitlement_id,
            result="succeeded",
            reason=policy_decision.reason,
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database operation failed",
        ) from exc

    assignment = db.scalar(
        select(AccessAssignment)
        .options(
            joinedload(AccessAssignment.entitlement).joinedload(
                Entitlement.application
            )
        )
        .where(AccessAssignment.id == assignment_id)
    )

    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Access assignment not found",
        )

    return access_assignment_to_response(assignment)


@app.post("/access/revoke")
def revoke_access(
    access_data: AccessActionRequest,
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    requester = db.get(User, access_data.requester_id)

    if requester is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requester not found",
        )

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

    application_id = entitlement.application.id

    assignment = db.scalar(
        select(AccessAssignment).where(
            AccessAssignment.user_id == access_data.user_id,
            AccessAssignment.entitlement_id == access_data.entitlement_id,
        )
    )

    if assignment is None:
        try:
            create_audit_event(
                db,
                requester_id=access_data.requester_id,
                target_user_id=access_data.user_id,
                action="revoke",
                application_id=application_id,
                entitlement_id=access_data.entitlement_id,
                result="denied",
                reason="Access assignment not found",
            )
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database operation failed",
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Access assignment not found",
        )

    policy_decision = evaluate_revoke_policy(requester, user, entitlement)

    if not policy_decision.allowed:
        try:
            create_audit_event(
                db,
                requester_id=access_data.requester_id,
                target_user_id=access_data.user_id,
                action="revoke",
                application_id=application_id,
                entitlement_id=access_data.entitlement_id,
                result="denied",
                reason=policy_decision.reason,
            )
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database operation failed",
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=policy_decision.reason,
        )

    try:
        db.delete(assignment)
        create_audit_event(
            db,
            requester_id=access_data.requester_id,
            target_user_id=access_data.user_id,
            action="revoke",
            application_id=application_id,
            entitlement_id=access_data.entitlement_id,
            result="succeeded",
            reason="Access revoked",
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database operation failed",
        ) from exc

    return {
        "status": "revoked",
        "user_id": access_data.user_id,
        "entitlement_id": access_data.entitlement_id,
    }


@app.get("/audit-events", response_model=list[AuditEventResponse])
def list_audit_events(
    requester_id: int | None = None,
    target_user_id: int | None = None,
    result: AuditResult | None = None,
    action: AuditAction | None = None,
    db: Session = Depends(get_db),
) -> list[AuditEventResponse]:
    statement = select(AuditEvent).options(
        joinedload(AuditEvent.application),
        joinedload(AuditEvent.entitlement),
    )

    if requester_id is not None:
        statement = statement.where(AuditEvent.requester_id == requester_id)

    if target_user_id is not None:
        statement = statement.where(AuditEvent.target_user_id == target_user_id)

    if result is not None:
        statement = statement.where(AuditEvent.result == result)

    if action is not None:
        statement = statement.where(AuditEvent.action == action)

    events = db.scalars(
        statement.order_by(
            AuditEvent.created_at.desc(),
            AuditEvent.id.desc(),
        )
    ).all()

    return [audit_event_to_response(event) for event in events]
