from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import logging
from threading import Lock
from time import perf_counter

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from .audit_service import create_audit_event
from .auth import create_access_token, get_current_user, hash_password, verify_password
from .connectors.registry import ConnectorRegistry
from .config import get_auth_settings, get_cors_settings
from .database import Base, SessionLocal, engine, get_db
from .dependencies import get_connector_registry, get_delegation_service
from .health import build_health_report
from .connectors.routes import router as connector_router
from .delegation.enums import DelegatedAction
from .delegation.models import DelegationAssignment
from .delegation.routes import router as delegation_router
from .delegation.services import DelegationAuthorization, DelegationService
from .governance.models import (
    CertificationCampaign,
    CertificationDecision,
    CertificationReviewItem,
)
from .governance.routes import router as governance_router
from .graph.routes import router as graph_router
from .ai.routes import router as ai_router
from .models import (
    AccessAssignment,
    Application,
    AuditEvent,
    Entitlement,
    EnterpriseUserProfile,
    Group,
    GroupMember,
    ProvisioningHistory,
    ProvisioningJob,
    User,
)
from .observability import configure_logging, log_event, metrics_registry
from .policy_engine import evaluate_grant_policy, evaluate_revoke_policy
from .provisioning.routes import router as provisioning_router
from .remediation.models import RemediationJob
from .remediation.routes import router as remediation_router
from .rbac import forbidden_exception, require_roles
from .scim.errors import register_scim_exception_handlers
from .scim.routes import router as scim_router
from .schemas import (
    AccessActionRequest,
    AccessResponse,
    AuditAction,
    AuditEventResponse,
    AuditResult,
    ApplicationResponse,
    EntitlementResponse,
    HealthResponse,
    LoginRequest,
    RevokeAccessResponse,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from .request_context import (
    CORRELATION_ID_HEADER,
    create_request_context,
    reset_request_context,
    set_request_context,
)

SEED_USER_PASSWORD = "Password123!"
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
        "operator_role": "helpdesk",
    },
    {
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "department": "Engineering",
        "active": True,
        "operator_role": "security_admin",
    },
    {
        "name": "Ian Wright",
        "email": "ian@example.com",
        "department": "Engineering",
        "active": True,
        "operator_role": "iam_admin",
    },
    {
        "name": "Audit Reviewer",
        "email": "auditor@example.com",
        "department": "Compliance",
        "active": True,
        "operator_role": "auditor",
    },
    {
        "name": "Maya Patel",
        "email": "manager@example.com",
        "department": "Operations",
        "active": True,
        "operator_role": "manager",
    },
]

SEEDED_APPLICATIONS = [
    {"name": "Salesforce", "slug": "salesforce"},
    {"name": "Zendesk", "slug": "zendesk"},
    {"name": "Finance Portal", "slug": "finance-portal"},
    {"name": "GitHub", "slug": "github"},
    {"name": "SCIM Provisioning", "slug": "scim-provisioning"},
    {"name": "Connector Framework", "slug": "connector-framework"},
    {"name": "Governance", "slug": "governance"},
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
    {
        "application_slug": "scim-provisioning",
        "name": "SCIM User Lifecycle",
        "slug": "user-lifecycle",
    },
    {
        "application_slug": "scim-provisioning",
        "name": "SCIM Group Lifecycle",
        "slug": "group-lifecycle",
    },
    {
        "application_slug": "scim-provisioning",
        "name": "SCIM Enterprise User Extension",
        "slug": "enterprise-user-extension",
    },
    {
        "application_slug": "connector-framework",
        "name": "Connector Execution",
        "slug": "connector-execution",
    },
    {
        "application_slug": "governance",
        "name": "Access Review Certification",
        "slug": "access-review-certification",
    },
]

_database_initialization_lock = Lock()
_database_initialized = False
configure_logging()


def ensure_schema_compatibility() -> None:
    """Apply idempotent compatibility updates for pre-migration schemas."""
    inspector = inspect(engine)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    table_names = set(inspector.get_table_names())

    with engine.begin() as connection:
        if "operator_role" not in user_columns:
            connection.execute(
                text(
                    "ALTER TABLE users "
                    "ADD COLUMN operator_role VARCHAR(50) NOT NULL DEFAULT 'employee'"
                )
            )

        for table in (
            Group.__table__,
            GroupMember.__table__,
            EnterpriseUserProfile.__table__,
            ProvisioningJob.__table__,
            ProvisioningHistory.__table__,
            CertificationCampaign.__table__,
            CertificationReviewItem.__table__,
            CertificationDecision.__table__,
            RemediationJob.__table__,
            DelegationAssignment.__table__,
        ):
            if table.name not in table_names:
                table.create(connection, checkfirst=True)

        if "audit_events" in table_names:
            audit_columns = {
                column["name"]
                for column in inspector.get_columns("audit_events")
            }
            if "correlation_id" not in audit_columns:
                connection.execute(
                    text(
                        "ALTER TABLE audit_events "
                        "ADD COLUMN correlation_id VARCHAR(100)"
                    )
                )

        if "enterprise_user_profiles" in table_names:
            enterprise_columns = {
                column["name"]
                for column in inspector.get_columns("enterprise_user_profiles")
            }
            enterprise_column_definitions = {
                "employee_number": "VARCHAR(100)",
                "department": "VARCHAR(100)",
                "division": "VARCHAR(100)",
                "cost_center": "VARCHAR(100)",
                "organization": "VARCHAR(100)",
                "manager_id": "INTEGER",
                "created_at": "DATETIME",
                "updated_at": "DATETIME",
            }
            for column_name, column_type in enterprise_column_definitions.items():
                if column_name in enterprise_columns:
                    continue

                connection.execute(
                    text(
                        "ALTER TABLE enterprise_user_profiles "
                        f"ADD COLUMN {column_name} {column_type}"
                    )
                )

        if "password_hash" not in user_columns:
            connection.execute(
                text(
                    "ALTER TABLE users "
                    "ADD COLUMN password_hash VARCHAR(255) NOT NULL DEFAULT ''"
                )
            )


def seed_users() -> None:
    """Insert or update known seed users without duplicating rows."""
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
            user.operator_role = user_data["operator_role"]

            if not verify_password(SEED_USER_PASSWORD, user.password_hash):
                user.password_hash = hash_password(SEED_USER_PASSWORD)

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


def _record_delegated_success(
    delegation_service: DelegationService,
    authorization: DelegationAuthorization,
    *,
    actor: User,
    target_user: User,
    entitlement: Entitlement,
    action: DelegatedAction,
) -> None:
    if not authorization.delegated or authorization.assignment is None:
        return

    delegation_service.record_delegated_access_granted(
        actor=actor,
        target_user=target_user,
        entitlement=entitlement,
        action=action,
        assignment=authorization.assignment,
    )


def _record_delegated_denial(
    delegation_service: DelegationService,
    authorization: DelegationAuthorization,
    *,
    actor: User,
    target_user: User,
    entitlement: Entitlement,
    action: DelegatedAction,
    reason: str,
) -> None:
    if not authorization.delegated or authorization.assignment is None:
        return

    delegation_service.record_delegated_access_denied(
        actor=actor,
        target_user=target_user,
        entitlement=entitlement,
        action=action,
        reason=reason,
        assignment=authorization.assignment,
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
        correlation_id=event.correlation_id,
        created_at=event.created_at,
    )


def initialize_database() -> None:
    global _database_initialized

    if _database_initialized:
        return

    with _database_initialization_lock:
        if _database_initialized:
            return

        Base.metadata.create_all(bind=engine)
        ensure_schema_compatibility()
        seed_users()
        seed_applications_and_entitlements()
        _database_initialized = True


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    initialize_database()
    yield


app = FastAPI(
    title="AccessIQ",
    version="0.1.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Authentication", "description": "Login and token issuance."},
        {"name": "Users", "description": "User management and lookup."},
        {
            "name": "Applications",
            "description": "Application and entitlement reference data.",
        },
        {"name": "Access", "description": "Access assignment operations."},
        {"name": "Audit", "description": "Audit event inspection."},
        {"name": "Health", "description": "Service health and metadata."},
        {
            "name": "SCIM",
            "description": (
                "SCIM 2.0 protocol metadata endpoints for enterprise identity "
                "provider integration."
            ),
        },
        {
            "name": "Connectors",
            "description": (
                "Provisioning connector metadata and deterministic health checks."
            ),
        },
        {
            "name": "Provisioning",
            "description": (
                "Provisioning job and immutable provisioning history inspection."
            ),
        },
        {
            "name": "Access Reviews",
            "description": (
                "Identity governance certification campaigns, review items, "
                "and certification decisions."
            ),
        },
        {
            "name": "Remediation",
            "description": (
                "Governance-driven remediation jobs executed through the "
                "existing provisioning infrastructure."
            ),
        },
        {
            "name": "Delegation",
            "description": (
                "Scoped delegated administration assignments and lifecycle "
                "operations."
            ),
        },
        {
            "name": "Authorization Graph",
            "description": (
                "Deterministic authorization graph traversal, evidence, and export."
            ),
        },
        {
            "name": "AI Context",
            "description": (
                "Deterministic evidence retrieval, prompt assembly, and grounded "
                "provider-backed explanations."
            ),
        },
    ],
)

register_scim_exception_handlers(app)
cors_settings = get_cors_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_settings.allowed_origins,
    allow_credentials=cors_settings.allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(scim_router)
app.include_router(connector_router)
app.include_router(provisioning_router)
app.include_router(governance_router)
app.include_router(remediation_router)
app.include_router(delegation_router)
app.include_router(graph_router)
app.include_router(ai_router)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    context = create_request_context(request)
    token = set_request_context(context)
    started_at = perf_counter()
    metrics_registry.increment("http_requests_total")

    try:
        try:
            initialize_database()
            response = await call_next(request)
        except Exception:
            metrics_registry.increment("http_request_errors_total")
            log_event(
                "http_request",
                status="error",
                level=logging.ERROR,
                method=request.method,
                path=request.url.path,
                duration_ms=round((perf_counter() - started_at) * 1000, 3),
            )
            raise

        response.headers[CORRELATION_ID_HEADER] = context.correlation_id
        if response.status_code >= 400:
            metrics_registry.increment("http_request_errors_total")

        log_event(
            "http_request",
            status="succeeded" if response.status_code < 500 else "failed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((perf_counter() - started_at) * 1000, 3),
        )

        return response
    finally:
        reset_request_context(token)


@app.get(
    "/",
    tags=["Health"],
    summary="Read service metadata",
    description="Returns basic service metadata and the documentation path.",
)
def read_root() -> dict[str, str]:
    return {
        "service": "AccessIQ",
        "documentation": "/docs",
    }


@app.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    tags=["Health"],
    summary="Check service health",
    description="Checks that the API can reach its configured database.",
)
def health_check(
    db: Session = Depends(get_db),
    registry: ConnectorRegistry = Depends(get_connector_registry),
) -> HealthResponse:
    try:
        return build_health_report(db=db, registry=registry)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed",
        ) from exc


@app.post(
    "/login",
    response_model=TokenResponse,
    tags=["Authentication"],
    summary="Issue an access token",
    description="Authenticates a user and returns a JWT bearer token.",
)
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


@app.get(
    "/users",
    response_model=list[UserResponse],
    tags=["Users"],
    summary="List users",
    description="Returns all known users ordered by ID.",
)
def list_users(db: Session = Depends(get_db)) -> list[User]:
    users = db.scalars(select(User).order_by(User.id)).all()
    return list(users)


@app.get(
    "/users/{user_id}",
    response_model=UserResponse,
    tags=["Users"],
    summary="Get a user",
    description="Returns one user by ID.",
)
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
    tags=["Users"],
    summary="Create a user",
    description="Creates a user with an operator role and development password.",
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
        password_hash=hash_password(SEED_USER_PASSWORD),
    )

    db.add(user)
    db.commit()
    db.refresh(user)
    metrics_registry.increment("users_created_total")

    return user


@app.get(
    "/applications",
    response_model=list[ApplicationResponse],
    tags=["Applications"],
    summary="List applications",
    description="Returns seeded applications available for entitlement lookup.",
)
def list_applications(db: Session = Depends(get_db)) -> list[Application]:
    applications = db.scalars(select(Application).order_by(Application.id)).all()
    return list(applications)


@app.get(
    "/applications/{application_id}/entitlements",
    response_model=list[EntitlementResponse],
    tags=["Applications"],
    summary="List application entitlements",
    description="Returns entitlements for one application.",
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


@app.get(
    "/users/{user_id}/access",
    response_model=list[AccessResponse],
    tags=["Access"],
    summary="List user access",
    description="Returns active access assignments for one user.",
)
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
    tags=["Access"],
    summary="Grant access",
    description=(
        "Requires a bearer token for a security_admin or iam_admin user. "
        "API RBAC runs before business policy evaluation and audit logging."
    ),
)
def grant_access(
    access_data: AccessActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    delegation_service: DelegationService = Depends(get_delegation_service),
) -> AccessResponse:
    user = db.get(User, access_data.target_user_id)

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
    authorization = delegation_service.authorize_access_action(
        actor=current_user,
        target_user=user,
        entitlement=entitlement,
        action=DelegatedAction.GRANT_ACCESS,
    )
    if not authorization.allowed:
        try:
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database operation failed",
            ) from exc

        delegation_service.publish_pending_events()
        raise forbidden_exception()

    existing_assignment = db.scalar(
        select(AccessAssignment).where(
            AccessAssignment.user_id == access_data.target_user_id,
            AccessAssignment.entitlement_id == access_data.entitlement_id,
        )
    )

    if existing_assignment is not None:
        try:
            _record_delegated_denial(
                delegation_service,
                authorization,
                actor=current_user,
                target_user=user,
                entitlement=entitlement,
                action=DelegatedAction.GRANT_ACCESS,
                reason="User already has this access",
            )
            create_audit_event(
                db,
                requester_id=current_user.id,
                target_user_id=access_data.target_user_id,
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

        delegation_service.publish_pending_events()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already has this access",
        )

    policy_decision = evaluate_grant_policy(
        current_user,
        user,
        entitlement,
        delegation_role=authorization.delegation_role,
    )

    if not policy_decision.allowed:
        try:
            _record_delegated_denial(
                delegation_service,
                authorization,
                actor=current_user,
                target_user=user,
                entitlement=entitlement,
                action=DelegatedAction.GRANT_ACCESS,
                reason=policy_decision.reason,
            )
            create_audit_event(
                db,
                requester_id=current_user.id,
                target_user_id=access_data.target_user_id,
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

        delegation_service.publish_pending_events()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=policy_decision.reason,
        )

    assignment = AccessAssignment(
        user_id=access_data.target_user_id,
        entitlement_id=access_data.entitlement_id,
    )

    try:
        db.add(assignment)
        db.flush()
        assignment_id = assignment.id
        _record_delegated_success(
            delegation_service,
            authorization,
            actor=current_user,
            target_user=user,
            entitlement=entitlement,
            action=DelegatedAction.GRANT_ACCESS,
        )
        create_audit_event(
            db,
            requester_id=current_user.id,
            target_user_id=access_data.target_user_id,
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

    delegation_service.publish_pending_events()

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


@app.post(
    "/access/revoke",
    response_model=RevokeAccessResponse,
    tags=["Access"],
    summary="Revoke access",
    description=(
        "Requires a bearer token for a security_admin or iam_admin user. "
        "API RBAC runs before business policy evaluation and audit logging."
    ),
)
def revoke_access(
    access_data: AccessActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    delegation_service: DelegationService = Depends(get_delegation_service),
) -> RevokeAccessResponse:
    user = db.get(User, access_data.target_user_id)

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
    authorization = delegation_service.authorize_access_action(
        actor=current_user,
        target_user=user,
        entitlement=entitlement,
        action=DelegatedAction.REVOKE_ACCESS,
    )
    if not authorization.allowed:
        try:
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database operation failed",
            ) from exc

        delegation_service.publish_pending_events()
        raise forbidden_exception()

    assignment = db.scalar(
        select(AccessAssignment).where(
            AccessAssignment.user_id == access_data.target_user_id,
            AccessAssignment.entitlement_id == access_data.entitlement_id,
        )
    )

    if assignment is None:
        try:
            _record_delegated_denial(
                delegation_service,
                authorization,
                actor=current_user,
                target_user=user,
                entitlement=entitlement,
                action=DelegatedAction.REVOKE_ACCESS,
                reason="Access assignment not found",
            )
            create_audit_event(
                db,
                requester_id=current_user.id,
                target_user_id=access_data.target_user_id,
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

        delegation_service.publish_pending_events()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Access assignment not found",
        )

    policy_decision = evaluate_revoke_policy(
        current_user,
        user,
        entitlement,
        delegation_role=authorization.delegation_role,
    )

    if not policy_decision.allowed:
        try:
            _record_delegated_denial(
                delegation_service,
                authorization,
                actor=current_user,
                target_user=user,
                entitlement=entitlement,
                action=DelegatedAction.REVOKE_ACCESS,
                reason=policy_decision.reason,
            )
            create_audit_event(
                db,
                requester_id=current_user.id,
                target_user_id=access_data.target_user_id,
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

        delegation_service.publish_pending_events()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=policy_decision.reason,
        )

    try:
        db.delete(assignment)
        _record_delegated_success(
            delegation_service,
            authorization,
            actor=current_user,
            target_user=user,
            entitlement=entitlement,
            action=DelegatedAction.REVOKE_ACCESS,
        )
        create_audit_event(
            db,
            requester_id=current_user.id,
            target_user_id=access_data.target_user_id,
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

    delegation_service.publish_pending_events()

    return RevokeAccessResponse(
        status="revoked",
        user_id=access_data.target_user_id,
        entitlement_id=access_data.entitlement_id,
    )


@app.get(
    "/audit-events",
    response_model=list[AuditEventResponse],
    tags=["Audit"],
    summary="List audit events",
    description=(
        "Requires a bearer token for a security_admin, iam_admin, or auditor "
        "user. Returns audit events newest first, optionally filtered by query "
        "parameters."
    ),
)
def list_audit_events(
    requester_id: int | None = None,
    target_user_id: int | None = None,
    result: AuditResult | None = None,
    action: AuditAction | None = None,
    correlation_id: str | None = None,
    current_user: User = Depends(
        require_roles("security_admin", "iam_admin", "auditor")
    ),
    db: Session = Depends(get_db),
) -> list[AuditEventResponse]:
    del current_user

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

    if correlation_id is not None:
        statement = statement.where(AuditEvent.correlation_id == correlation_id)

    events = db.scalars(
        statement.order_by(
            AuditEvent.created_at.desc(),
            AuditEvent.id.desc(),
        )
    ).all()

    return [audit_event_to_response(event) for event in events]
