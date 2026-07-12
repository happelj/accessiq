from fastapi import APIRouter, Depends, HTTPException, status

from ..models import User
from ..rbac import require_roles
from ..schemas import ConnectorHealthResponse, ConnectorResponse
from .base import IdentityConnector
from .exceptions import UnknownConnectorError
from .registry import ConnectorRegistry, build_connector_registry

router = APIRouter(prefix="/connectors", tags=["Connectors"])


def get_connector_registry() -> ConnectorRegistry:
    return build_connector_registry()


@router.get(
    "",
    response_model=list[ConnectorResponse],
    summary="List connectors",
    description=(
        "Lists enabled provisioning connectors and their supported operations. "
        "Connectors are deterministic mock implementations in this milestone."
    ),
)
def list_connectors(
    current_user: User = Depends(
        require_roles("security_admin", "iam_admin", "auditor")
    ),
    registry: ConnectorRegistry = Depends(get_connector_registry),
) -> list[ConnectorResponse]:
    del current_user
    return [_connector_to_response(connector) for connector in registry.list()]


@router.get(
    "/{name}",
    response_model=ConnectorResponse,
    summary="Get connector metadata",
    description="Returns one connector's metadata and supported operations.",
)
def get_connector(
    name: str,
    current_user: User = Depends(
        require_roles("security_admin", "iam_admin", "auditor")
    ),
    registry: ConnectorRegistry = Depends(get_connector_registry),
) -> ConnectorResponse:
    del current_user
    try:
        connector = registry.get(name)
    except UnknownConnectorError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found",
        ) from exc

    return _connector_to_response(connector)


@router.get(
    "/{name}/health",
    response_model=ConnectorHealthResponse,
    summary="Check connector health",
    description="Returns deterministic connector health for administrative checks.",
)
def get_connector_health(
    name: str,
    current_user: User = Depends(
        require_roles("security_admin", "iam_admin", "auditor")
    ),
    registry: ConnectorRegistry = Depends(get_connector_registry),
) -> ConnectorHealthResponse:
    del current_user
    try:
        connector = registry.get(name)
    except UnknownConnectorError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found",
        ) from exc

    return ConnectorHealthResponse(**connector.health_check().to_dict())


def _connector_to_response(connector: IdentityConnector) -> ConnectorResponse:
    return ConnectorResponse(
        name=connector.name,
        display_name=connector.display_name,
        enabled=connector.enabled,
        supported_operations=[
            operation.value for operation in connector.supported_operations
        ],
    )
