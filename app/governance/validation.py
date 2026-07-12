from .enums import CampaignStatus


VALID_CAMPAIGN_TRANSITIONS = {
    CampaignStatus.DRAFT: {CampaignStatus.ACTIVE, CampaignStatus.CANCELLED},
    CampaignStatus.ACTIVE: {CampaignStatus.COMPLETED, CampaignStatus.CANCELLED},
    CampaignStatus.COMPLETED: set(),
    CampaignStatus.CANCELLED: set(),
}


def validate_campaign_transition(
    current_status: str,
    next_status: CampaignStatus,
) -> None:
    try:
        current = CampaignStatus(current_status)
    except ValueError as exc:
        raise ValueError(f"Unknown campaign status: {current_status}") from exc

    if next_status not in VALID_CAMPAIGN_TRANSITIONS[current]:
        raise ValueError(
            f"Cannot transition campaign from {current.value} to {next_status.value}"
        )
