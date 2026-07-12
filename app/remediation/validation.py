from .enums import RemediationType


APPLICATION_CONNECTOR_NAMES = {
    "salesforce": "salesforce",
    "github": "github",
    "zendesk": "zendesk",
    "finance-portal": "finance",
}


def connector_name_for_application(application_slug: str) -> str:
    connector_name = APPLICATION_CONNECTOR_NAMES.get(application_slug)
    if connector_name is None:
        raise ValueError(
            f"No enabled remediation connector mapping for application "
            f"{application_slug!r}"
        )

    return connector_name


def validate_remediation_type(value: str) -> RemediationType:
    try:
        return RemediationType(value)
    except ValueError as exc:
        raise ValueError(f"Unsupported remediation type: {value}") from exc
