from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import ReleaseSettings
from ..models import ReleaseDeployment
from .schemas import DeploymentHistoryResponse, ReleaseMetadataResponse


@dataclass(frozen=True)
class DeploymentHistoryFilters:
    environment: str | None = None
    status: str | None = None


class ReleaseService:
    def __init__(self, db: Session, settings: ReleaseSettings) -> None:
        self.db = db
        self.settings = settings

    def current_metadata(self) -> ReleaseMetadataResponse:
        return ReleaseMetadataResponse(
            service="AccessIQ",
            version=self.settings.release_version,
            environment=self.settings.environment,
            git_sha=self.settings.git_sha,
            git_tag=self.settings.git_tag,
            build_timestamp=self.settings.build_timestamp,
            docker_image=self.settings.docker_image,
            image_digest=self.settings.image_digest,
            helm_chart_version=self.settings.helm_chart_version,
            terraform_version=self.settings.terraform_version,
        )

    def list_deployments(
        self,
        *,
        filters: DeploymentHistoryFilters | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ReleaseDeployment]:
        resolved_filters = filters or DeploymentHistoryFilters()
        statement = select(ReleaseDeployment)

        if resolved_filters.environment is not None:
            statement = statement.where(
                ReleaseDeployment.environment == resolved_filters.environment
            )

        if resolved_filters.status is not None:
            statement = statement.where(
                ReleaseDeployment.status == resolved_filters.status
            )

        statement = statement.order_by(
            ReleaseDeployment.deployed_at.desc(),
            ReleaseDeployment.id.desc(),
        )

        return list(self.db.scalars(statement.offset(offset).limit(limit)).all())

    def current_deployment(self) -> ReleaseDeployment | None:
        statement = (
            select(ReleaseDeployment)
            .where(ReleaseDeployment.environment == self.settings.environment)
            .order_by(
                ReleaseDeployment.deployed_at.desc(),
                ReleaseDeployment.id.desc(),
            )
            .limit(1)
        )
        return self.db.scalar(statement)

    def record_current_deployment(self) -> ReleaseDeployment:
        existing = self._find_matching_current_deployment()

        if existing is not None:
            return existing

        deployment = ReleaseDeployment(
            environment=self.settings.environment,
            deployed_at=self._deployment_time(),
            version=self.settings.release_version,
            git_sha=self.settings.git_sha,
            git_tag=self.settings.git_tag,
            build_timestamp=self.settings.build_timestamp,
            docker_image=self.settings.docker_image,
            image_digest=self.settings.image_digest,
            helm_chart_version=self.settings.helm_chart_version,
            helm_revision=self.settings.helm_revision,
            terraform_version=self.settings.terraform_version,
            operator=self.settings.deployment_operator,
            status=self.settings.deployment_status,
        )
        self.db.add(deployment)
        self.db.flush()
        return deployment

    def _find_matching_current_deployment(self) -> ReleaseDeployment | None:
        statement = (
            select(ReleaseDeployment)
            .where(
                ReleaseDeployment.environment == self.settings.environment,
                ReleaseDeployment.version == self.settings.release_version,
                ReleaseDeployment.git_sha == self.settings.git_sha,
                ReleaseDeployment.status == self.settings.deployment_status,
                ReleaseDeployment.operator == self.settings.deployment_operator,
            )
            .order_by(ReleaseDeployment.deployed_at.desc(), ReleaseDeployment.id.desc())
            .limit(1)
        )
        candidates = self.db.scalars(statement).all()

        for deployment in candidates:
            if _matches_optional(
                deployment.helm_revision,
                self.settings.helm_revision,
            ) and _matches_optional(
                deployment.docker_image, self.settings.docker_image
            ):
                return deployment

        return None

    def _deployment_time(self) -> datetime:
        for value in (self.settings.deployed_at, self.settings.build_timestamp):
            parsed = _parse_datetime(value)
            if parsed is not None:
                return parsed

        return datetime.now(UTC)


def deployment_to_response(
    deployment: ReleaseDeployment,
) -> DeploymentHistoryResponse:
    return DeploymentHistoryResponse.model_validate(deployment)


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)

    return parsed.astimezone(UTC)


def _matches_optional(left: str | None, right: str | None) -> bool:
    return (left or "") == (right or "")
