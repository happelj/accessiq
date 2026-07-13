from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from .config import ConnectorSettings, get_connector_settings
from .connectors import ProvisioningOrchestrator
from .connectors.registry import ConnectorRegistry, build_connector_registry
from .database import get_db
from .delegation.services import DelegationService
from .governance.services import CampaignService, ReviewService
from .remediation.services import RemediationService
from .services.provisioning_job_service import ProvisioningJobService


def get_connector_registry(
    settings: ConnectorSettings = Depends(get_connector_settings),
) -> ConnectorRegistry:
    return build_connector_registry(settings)


def get_provisioning_orchestrator(
    registry: ConnectorRegistry = Depends(get_connector_registry),
) -> ProvisioningOrchestrator:
    return ProvisioningOrchestrator(registry=registry)


def get_provisioning_job_service(
    db: Session = Depends(get_db),
) -> ProvisioningJobService:
    return ProvisioningJobService(db)


def get_campaign_service(db: Session = Depends(get_db)) -> CampaignService:
    return CampaignService(db)


def get_review_service(db: Session = Depends(get_db)) -> ReviewService:
    return ReviewService(db)


def get_remediation_service(
    db: Session = Depends(get_db),
    orchestrator: ProvisioningOrchestrator = Depends(get_provisioning_orchestrator),
) -> RemediationService:
    return RemediationService(db, orchestrator=orchestrator)


def get_delegation_service(db: Session = Depends(get_db)) -> DelegationService:
    return DelegationService(db)
