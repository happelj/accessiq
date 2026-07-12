from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import DelegationRole, DelegationScopeType


class DelegationAssignmentCreate(BaseModel):
    delegate_user_id: int = Field(description="User receiving delegated authority.")
    scope_type: DelegationScopeType = Field(
        description="Scope type for delegated authority."
    )
    scope_id: int = Field(description="ID of the application, group, or entitlement.")
    delegation_role: DelegationRole = Field(
        description="Delegation role granted within the scope."
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Optional UTC expiration timestamp.",
    )


class DelegationAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    delegate_user_id: int
    scope_type: DelegationScopeType
    scope_id: int
    delegation_role: DelegationRole
    created_by: int
    created_at: datetime
    expires_at: datetime | None
    active: bool
