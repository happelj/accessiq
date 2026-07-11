from .models import Entitlement, User
from .schemas import PolicyDecision


def is_administrator_entitlement(entitlement: Entitlement) -> bool:
    return entitlement.slug.lower() == "administrator"


def evaluate_grant_policy(
    requester: User,
    target_user: User,
    entitlement: Entitlement,
) -> PolicyDecision:
    """Evaluate grant rules in deterministic priority order."""
    requester_role = requester.operator_role.lower()
    application_slug = entitlement.application.slug.lower()

    if not target_user.active:
        return PolicyDecision(allowed=False, reason="Target user is inactive")

    if not requester.active:
        return PolicyDecision(allowed=False, reason="Requester is inactive")

    if requester_role == "auditor":
        return PolicyDecision(allowed=False, reason="Auditors cannot grant access")

    if requester_role == "employee":
        return PolicyDecision(allowed=False, reason="Employees cannot grant access")

    if (
        application_slug == "finance-portal"
        and target_user.department.lower() != "finance"
    ):
        return PolicyDecision(
            allowed=False,
            reason="Finance Portal access is restricted to Finance employees",
        )

    if is_administrator_entitlement(entitlement) and requester_role != "administrator":
        return PolicyDecision(
            allowed=False,
            reason="Requester lacks permission to grant administrator access",
        )

    if requester_role in {"administrator", "help_desk"}:
        return PolicyDecision(allowed=True, reason="Access request approved")

    return PolicyDecision(
        allowed=False,
        reason="Requester role is not allowed to grant access",
    )


def evaluate_revoke_policy(
    requester: User,
    target_user: User,
    entitlement: Entitlement,
) -> PolicyDecision:
    """Evaluate revoke rules in deterministic priority order."""
    del target_user

    requester_role = requester.operator_role.lower()

    if not requester.active:
        return PolicyDecision(allowed=False, reason="Requester is inactive")

    if requester_role == "auditor":
        return PolicyDecision(allowed=False, reason="Auditors cannot revoke access")

    if requester_role == "employee":
        return PolicyDecision(allowed=False, reason="Employees cannot revoke access")

    if is_administrator_entitlement(entitlement) and requester_role != "administrator":
        return PolicyDecision(
            allowed=False,
            reason="Requester lacks permission to revoke administrator access",
        )

    if requester_role in {"administrator", "help_desk"}:
        return PolicyDecision(allowed=True, reason="Access request approved")

    return PolicyDecision(
        allowed=False,
        reason="Requester role is not allowed to revoke access",
    )
