CANONICAL_OPERATOR_ROLES = frozenset(
    {
        "security_admin",
        "iam_admin",
        "auditor",
        "helpdesk",
        "manager",
        "employee",
    }
)

LEGACY_OPERATOR_ROLE_ALIASES = {
    "administrator": "security_admin",
    "help_desk": "helpdesk",
}

SUPPORTED_OPERATOR_ROLES = CANONICAL_OPERATOR_ROLES | frozenset(
    LEGACY_OPERATOR_ROLE_ALIASES
)


def normalize_operator_role(role: str) -> str:
    normalized_role = role.strip().lower().replace("-", "_")
    return LEGACY_OPERATOR_ROLE_ALIASES.get(normalized_role, normalized_role)


def validate_operator_role(role: str) -> str:
    normalized_role = normalize_operator_role(role)

    if normalized_role not in CANONICAL_OPERATOR_ROLES:
        raise ValueError(f"Unsupported operator role: {role}")

    return normalized_role
