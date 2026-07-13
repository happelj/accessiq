from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError

from ..dependencies import get_delegation_service
from ..models import User
from ..rbac import require_roles
from .enums import DelegationRole, DelegationScopeType
from .models import DelegationAssignment
from .schemas import DelegationAssignmentCreate, DelegationAssignmentResponse
from .services import (
    DelegationAssignmentFilters,
    DelegationAssignmentNotFoundError,
    DelegationDelegateNotFoundError,
    DelegationScopeNotFoundError,
    DelegationService,
    DelegationServiceError,
    DuplicateDelegationAssignmentError,
    ExpiredDelegationAssignmentError,
    InactiveDelegateUserError,
    InactiveDelegationAssignmentError,
    InvalidDelegationScopeError,
    UnsupportedDelegationSortFieldError,
    UnsupportedDelegationSortOrderError,
)

router = APIRouter(prefix="/delegation", tags=["Delegation"])

DELEGATION_ADMIN_ROLES = ("security_admin", "iam_admin")


@router.post(
    "/assignments",
    response_model=DelegationAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign delegated administration",
    description=(
        "Creates an active delegated administration assignment for an "
        "application, group, or entitlement scope."
    ),
)
def assign_delegation(
    payload: DelegationAssignmentCreate = Body(
        ...,
        openapi_examples={
            "applicationHelpdesk": {
                "summary": "Delegate Salesforce helpdesk administration",
                "value": {
                    "delegate_user_id": 2,
                    "scope_type": "APPLICATION",
                    "scope_id": 1,
                    "delegation_role": "HELPDESK_DELEGATE",
                },
            }
        },
    ),
    current_user: User = Depends(require_roles(*DELEGATION_ADMIN_ROLES)),
    service: DelegationService = Depends(get_delegation_service),
) -> DelegationAssignmentResponse:
    db = service.db
    try:
        assignment = service.assign_delegate(
            delegate_user_id=payload.delegate_user_id,
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            delegation_role=payload.delegation_role,
            actor=current_user,
            expires_at=payload.expires_at,
        )
        db.commit()
    except DelegationServiceError as exc:
        db.rollback()
        _raise_delegation_http_error(exc)
    except SQLAlchemyError as exc:
        db.rollback()
        raise _database_error() from exc

    service.publish_pending_events()

    return _assignment_to_response(assignment)


@router.get(
    "/assignments",
    response_model=list[DelegationAssignmentResponse],
    summary="List delegated administration assignments",
    description=(
        "Lists delegation assignments with filters for delegate, scope, role, "
        "active state, pagination, and deterministic sorting."
    ),
)
def list_delegation_assignments(
    delegate_user_id: int | None = None,
    scope_type: DelegationScopeType | None = None,
    scope_id: int | None = None,
    delegation_role: DelegationRole | None = None,
    active: bool | None = None,
    start_index: int = Query(default=1, ge=1),
    count: int = Query(default=100, ge=1, le=500),
    sort_by: str | None = Query(default="created_at"),
    sort_order: str = Query(default="descending"),
    current_user: User = Depends(require_roles(*DELEGATION_ADMIN_ROLES)),
    service: DelegationService = Depends(get_delegation_service),
) -> list[DelegationAssignmentResponse]:
    del current_user
    try:
        assignments = service.list_assignments(
            filters=DelegationAssignmentFilters(
                delegate_user_id=delegate_user_id,
                scope_type=scope_type.value if scope_type is not None else None,
                scope_id=scope_id,
                delegation_role=delegation_role.value
                if delegation_role is not None
                else None,
                active=active,
            ),
            offset=start_index - 1,
            limit=count,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except DelegationServiceError as exc:
        _raise_delegation_http_error(exc)

    return [_assignment_to_response(assignment) for assignment in assignments]


@router.get(
    "/assignments/{assignment_id}",
    response_model=DelegationAssignmentResponse,
    summary="Get delegated administration assignment",
    description="Returns one delegation assignment by ID.",
)
def get_delegation_assignment(
    assignment_id: int,
    current_user: User = Depends(require_roles(*DELEGATION_ADMIN_ROLES)),
    service: DelegationService = Depends(get_delegation_service),
) -> DelegationAssignmentResponse:
    del current_user
    try:
        assignment = service.lookup_assignment(assignment_id)
    except DelegationServiceError as exc:
        _raise_delegation_http_error(exc)

    return _assignment_to_response(assignment)


@router.delete(
    "/assignments/{assignment_id}",
    response_model=DelegationAssignmentResponse,
    summary="Remove delegated administration assignment",
    description="Marks one delegation assignment inactive.",
)
def remove_delegation_assignment(
    assignment_id: int,
    current_user: User = Depends(require_roles(*DELEGATION_ADMIN_ROLES)),
    service: DelegationService = Depends(get_delegation_service),
) -> DelegationAssignmentResponse:
    db = service.db
    try:
        assignment = service.remove_delegate(assignment_id, actor=current_user)
        db.commit()
    except DelegationServiceError as exc:
        db.rollback()
        _raise_delegation_http_error(exc)
    except SQLAlchemyError as exc:
        db.rollback()
        raise _database_error() from exc

    service.publish_pending_events()

    return _assignment_to_response(assignment)


def _assignment_to_response(
    assignment: DelegationAssignment,
) -> DelegationAssignmentResponse:
    return DelegationAssignmentResponse(
        id=assignment.id,
        delegate_user_id=assignment.delegate_user_id,
        scope_type=DelegationScopeType(assignment.scope_type),
        scope_id=assignment.scope_id,
        delegation_role=DelegationRole(assignment.delegation_role),
        created_by=assignment.created_by,
        created_at=assignment.created_at,
        expires_at=assignment.expires_at,
        active=assignment.active,
    )


def _database_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database operation failed",
    )


def _raise_delegation_http_error(error: DelegationServiceError) -> None:
    if isinstance(
        error,
        (
            DelegationAssignmentNotFoundError,
            DelegationDelegateNotFoundError,
            DelegationScopeNotFoundError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    if isinstance(
        error,
        (
            DuplicateDelegationAssignmentError,
            InactiveDelegateUserError,
            InactiveDelegationAssignmentError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    if isinstance(
        error,
        (
            ExpiredDelegationAssignmentError,
            InvalidDelegationScopeError,
            UnsupportedDelegationSortFieldError,
            UnsupportedDelegationSortOrderError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=str(error),
    ) from error
