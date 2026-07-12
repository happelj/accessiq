from .enums import DelegationRole, DelegationScopeType

SCOPE_ROLE_MATRIX: dict[DelegationScopeType, frozenset[DelegationRole]] = {
    DelegationScopeType.APPLICATION: frozenset(
        {
            DelegationRole.APPLICATION_OWNER,
            DelegationRole.APPLICATION_ADMINISTRATOR,
            DelegationRole.ACCESS_REVIEWER,
            DelegationRole.HELPDESK_DELEGATE,
        }
    ),
    DelegationScopeType.ENTITLEMENT: frozenset(
        {
            DelegationRole.APPLICATION_OWNER,
            DelegationRole.APPLICATION_ADMINISTRATOR,
            DelegationRole.HELPDESK_DELEGATE,
        }
    ),
    DelegationScopeType.GROUP: frozenset(
        {
            DelegationRole.GROUP_OWNER,
            DelegationRole.GROUP_ADMINISTRATOR,
        }
    ),
}

ACCESS_CHANGE_DELEGATION_ROLES = frozenset(
    {
        DelegationRole.APPLICATION_OWNER,
        DelegationRole.APPLICATION_ADMINISTRATOR,
        DelegationRole.HELPDESK_DELEGATE,
    }
)


def role_supports_scope(
    scope_type: DelegationScopeType,
    delegation_role: DelegationRole,
) -> bool:
    return delegation_role in SCOPE_ROLE_MATRIX[scope_type]


def role_supports_access_change(delegation_role: str) -> bool:
    try:
        parsed_role = DelegationRole(delegation_role)
    except ValueError:
        return False

    return parsed_role in ACCESS_CHANGE_DELEGATION_ROLES
