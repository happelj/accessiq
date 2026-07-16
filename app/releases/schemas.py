from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReleaseMetadataResponse(BaseModel):
    service: str = Field(description="Service name.")
    version: str = Field(description="Human-facing release version.")
    environment: str = Field(description="Runtime deployment environment.")
    git_sha: str = Field(description="Git SHA used to build the release.")
    git_tag: str | None = Field(
        default=None, description="Git tag, when deployed from a tag."
    )
    build_timestamp: str | None = Field(
        default=None,
        description="UTC build timestamp captured by the deployment workflow.",
    )
    docker_image: str | None = Field(
        default=None,
        description="Backend Docker image reference deployed for this release.",
    )
    image_digest: str | None = Field(
        default=None,
        description="Backend Docker image digest, when available.",
    )
    helm_chart_version: str = Field(
        description="Helm chart version used for deployment."
    )
    terraform_version: str | None = Field(
        default=None,
        description="Terraform version or version constraint for the provisioned environment.",
    )


class DeploymentHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    environment: str
    deployed_at: datetime
    version: str
    git_sha: str
    git_tag: str | None
    build_timestamp: str | None
    docker_image: str | None
    image_digest: str | None
    helm_chart_version: str | None
    helm_revision: str | None
    terraform_version: str | None
    operator: str
    status: str


class CurrentReleaseResponse(BaseModel):
    metadata: ReleaseMetadataResponse
    deployment: DeploymentHistoryResponse | None = Field(
        default=None,
        description="Most recent application-level deployment record for the current environment.",
    )
