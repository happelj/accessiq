from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

OperatorRole = Literal["administrator", "help_desk", "auditor", "employee"]
AuditAction = Literal["grant", "revoke"]
AuditResult = Literal["allowed", "denied", "succeeded"]


class HealthResponse(BaseModel):
    status: str


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    department: str = Field(min_length=1, max_length=100)
    active: bool = True
    operator_role: OperatorRole = "employee"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    department: str
    active: bool
    operator_role: OperatorRole


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


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

    target_user_id: int
    entitlement_id: int


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
    created_at: datetime
