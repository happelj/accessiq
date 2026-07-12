from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

OperatorRole = Literal[
    "security_admin",
    "iam_admin",
    "auditor",
    "helpdesk",
    "manager",
    "employee",
    "administrator",
    "help_desk",
]
AuditAction = Literal[
    "grant",
    "revoke",
    "scim_user_create",
    "scim_user_update",
    "scim_user_deactivate",
    "scim_user_provisioning_failure",
    "scim_group_create",
    "scim_group_update",
    "scim_group_rename",
    "scim_group_member_add",
    "scim_group_member_remove",
    "scim_group_members_replace",
    "scim_group_provisioning_failure",
    "scim_enterprise_profile_create",
    "scim_enterprise_profile_update",
    "scim_enterprise_manager_change",
    "scim_enterprise_department_change",
    "scim_enterprise_organization_change",
    "scim_enterprise_cost_center_change",
    "scim_enterprise_division_change",
    "scim_enterprise_employee_number_change",
    "scim_enterprise_provisioning_failure",
    "connector_invocation",
    "connector_success",
    "connector_failure",
    "connector_retry_scheduled",
    "connector_provisioning_completed",
    "provisioning_job_created",
    "provisioning_job_completed",
    "provisioning_job_failed",
    "provisioning_retry_recorded",
    "certification_campaign_created",
    "certification_campaign_started",
    "certification_campaign_cancelled",
    "certification_campaign_completed",
    "certification_review_approved",
    "certification_review_revoked",
    "certification_review_abstained",
    "certification_decision_updated",
    "remediation_created",
    "remediation_started",
    "remediation_completed",
    "remediation_failed",
]
AuditResult = Literal["allowed", "denied", "succeeded"]


class HealthResponse(BaseModel):
    status: str = Field(description="Current service health status.")


class UserCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=100,
        description="Display name for the user.",
    )
    email: EmailStr = Field(description="Unique email address for the user.")
    department: str = Field(
        min_length=1,
        max_length=100,
        description="Department used by policy evaluation.",
    )
    active: bool = Field(
        default=True,
        description="Whether the user is eligible for access decisions.",
    )
    operator_role: OperatorRole = Field(
        default="employee",
        description="API operator role assigned to the user.",
    )


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    department: str
    active: bool
    operator_role: OperatorRole


class LoginRequest(BaseModel):
    email: EmailStr = Field(description="User email address.")
    password: str = Field(min_length=1, description="User password.")


class TokenResponse(BaseModel):
    access_token: str = Field(description="JWT bearer token.")
    token_type: str = Field(description="Token type. Always bearer.")
    expires_in: int = Field(description="Token lifetime in seconds.")


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str


class EntitlementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    application_id: int


class AccessActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_user_id: int = Field(
        description="ID of the user whose access is being changed.",
    )
    entitlement_id: int = Field(
        description="ID of the entitlement to grant or revoke.",
    )


class PolicyDecision(BaseModel):
    allowed: bool
    reason: str


class AccessResponse(BaseModel):
    id: int
    user_id: int
    application_id: int
    application: str
    entitlement_id: int
    entitlement: str
    status: str
    granted_at: datetime


class RevokeAccessResponse(BaseModel):
    status: str
    user_id: int
    entitlement_id: int


class AuditEventResponse(BaseModel):
    id: int
    requester_id: int
    target_user_id: int
    action: str
    application_id: int
    application: str
    entitlement_id: int
    entitlement: str
    result: str
    reason: str
    correlation_id: str | None = None
    created_at: datetime


class ConnectorResponse(BaseModel):
    name: str
    display_name: str
    enabled: bool
    supported_operations: list[str]


class ConnectorHealthResponse(BaseModel):
    connector: str
    status: str
    message: str
    timestamp: datetime
    details: dict[str, object]


class ProvisioningJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    correlation_id: str
    connector: str
    operation: str
    target_type: str
    target_id: str | None
    status: str
    attempt_count: int
    retry_count: int
    max_attempts: int
    retryable: bool
    last_error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: float | None


class ProvisioningHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    correlation_id: str
    connector: str
    operation: str
    event_type: str
    status: str
    message: str
    attempt: int
    retryable: bool
    duration_ms: float | None
    details: dict[str, object]
    created_at: datetime
