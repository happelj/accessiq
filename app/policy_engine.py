from .models import Entitlement, User
from .roles import normalize_operator_role
from .schemas import PolicyDecision

ADMIN_POLICY_ROLES = {"security_admin", "iam_admin"}
HELPDESK_POLICY_ROLES = {"helpdesk"}
DELEGATED_ACCESS_POLICY_ROLES = {
    "APPLICATION_OWNER",
    "APPLICATION_ADMINISTRATOR",
    "HELPDESK_DELEGATE",
}
DELEGATED_ADMIN_POLICY_ROLES = {
    "APPLICATION_OWNER",
    "APPLICATION_ADMINISTRATOR",
}


def is_administrator_entitlement(entitlement: Entitlement) -> bool:
    return entitlement.slug.lower() == "administrator"


def evaluate_grant_policy(
    requester: User,
    target_user: User,
    entitlement: Entitlement,
    *,
    delegation_role: str | None = None,
) -> PolicyDecision:
    """Evaluate grant rules in deterministic priority order."""
    requester_role = normalize_operator_role(requester.operator_role)
    application_slug = entitlement.application.slug.lower()
    normalized_delegation_role = _normalize_delegation_role(delegation_role)

    if not target_user.active:
        return PolicyDecision(allowed=False, reason="Target user is inactive")

    if not requester.active:
        return PolicyDecision(allowed=False, reason="Requester is inactive")

    if normalized_delegation_role is None and requester_role == "auditor":
        return PolicyDecision(allowed=False, reason="Auditors cannot grant access")

    if normalized_delegation_role is None and requester_role == "employee":
        return PolicyDecision(allowed=False, reason="Employees cannot grant access")

    if (
        application_slug == "finance-portal"
        and target_user.department.lower() != "finance"
    ):
        return PolicyDecision(
            allowed=False,
            reason="Finance Portal access is restricted to Finance employees",
        )

    if (
        is_administrator_entitlement(entitlement)
        and normalized_delegation_role is not None
        and normalized_delegation_role not in DELEGATED_ADMIN_POLICY_ROLES
    ):
        return PolicyDecision(
            allowed=False,
            reason="Delegation does not permit administrator access changes",
        )

    if (
        is_administrator_entitlement(entitlement)
        and normalized_delegation_role is None
        and requester_role not in ADMIN_POLICY_ROLES
    ):
        return PolicyDecision(
            allowed=False,
            reason="Requester lacks permission to grant administrator access",
        )

    if normalized_delegation_role in DELEGATED_ACCESS_POLICY_ROLES:
        return PolicyDecision(
            allowed=True,
            reason="Delegated access request approved",
        )

    if requester_role in ADMIN_POLICY_ROLES | HELPDESK_POLICY_ROLES:
        return PolicyDecision(allowed=True, reason="Access request approved")

    return PolicyDecision(
        allowed=False,
        reason="Requester role is not allowed to grant access",
    )


def evaluate_revoke_policy(
    requester: User,
    target_user: User,
    entitlement: Entitlement,
    *,
    delegation_role: str | None = None,
) -> PolicyDecision:
    """Evaluate revoke rules in deterministic priority order."""
    del target_user

    requester_role = normalize_operator_role(requester.operator_role)
    normalized_delegation_role = _normalize_delegation_role(delegation_role)

    if not requester.active:
        return PolicyDecision(allowed=False, reason="Requester is inactive")

    if normalized_delegation_role is None and requester_role == "auditor":
        return PolicyDecision(allowed=False, reason="Auditors cannot revoke access")

    if normalized_delegation_role is None and requester_role == "employee":
        return PolicyDecision(allowed=False, reason="Employees cannot revoke access")

    if (
        is_administrator_entitlement(entitlement)
        and normalized_delegation_role is not None
        and normalized_delegation_role not in DELEGATED_ADMIN_POLICY_ROLES
    ):
        return PolicyDecision(
            allowed=False,
            reason="Delegation does not permit administrator access changes",
        )

    if (
        is_administrator_entitlement(entitlement)
        and normalized_delegation_role is None
        and requester_role not in ADMIN_POLICY_ROLES
    ):
        return PolicyDecision(
            allowed=False,
            reason="Requester lacks permission to revoke administrator access",
        )

    if normalized_delegation_role in DELEGATED_ACCESS_POLICY_ROLES:
        return PolicyDecision(
            allowed=True,
            reason="Delegated access request approved",
        )

    if requester_role in ADMIN_POLICY_ROLES | HELPDESK_POLICY_ROLES:
        return PolicyDecision(allowed=True, reason="Access request approved")

    return PolicyDecision(
        allowed=False,
        reason="Requester role is not allowed to revoke access",
    )


def _normalize_delegation_role(delegation_role: str | None) -> str | None:
    if delegation_role is None:
        return None

    return delegation_role.strip().upper().replace("-", "_")
