from enum import StrEnum


class CampaignStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ReviewItemStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"


class CertificationDecisionValue(StrEnum):
    APPROVE = "APPROVE"
    REVOKE = "REVOKE"
    ABSTAIN = "ABSTAIN"
