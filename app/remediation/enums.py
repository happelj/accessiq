from enum import StrEnum


class RemediationType(StrEnum):
    REVOKE_ENTITLEMENT = "REVOKE_ENTITLEMENT"
    REMOVE_GROUP_MEMBER = "REMOVE_GROUP_MEMBER"
    DISABLE_USER = "DISABLE_USER"


class RemediationStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
