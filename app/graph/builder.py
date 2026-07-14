from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..connectors.registry import ConnectorRegistry
from ..delegation.models import DelegationAssignment
from ..governance.models import CertificationCampaign, CertificationReviewItem
from ..models import (
    AccessAssignment,
    Application,
    AuditEvent,
    Entitlement,
    EnterpriseUserProfile,
    Group,
    GroupMember,
    ProvisioningHistory,
    ProvisioningJob,
    User,
)
from ..remediation.models import RemediationJob
from .models import AuthorizationGraph, EdgeType, GraphNode, NodeType, graph_node_id


def build_authorization_graph(
    db: Session,
    *,
    registry: ConnectorRegistry,
) -> AuthorizationGraph:
    graph = AuthorizationGraph()
    _add_identity_nodes(db, graph)
    _add_application_nodes(db, graph)
    _add_connector_nodes(graph, registry)
    _add_governance_nodes(db, graph)
    _add_operations_nodes(db, graph)
    _add_relationship_edges(db, graph)
    return graph


def _add_identity_nodes(db: Session, graph: AuthorizationGraph) -> None:
    for user in db.scalars(select(User).order_by(User.id)).all():
        graph.add_node(
            GraphNode(
                id=graph_node_id(NodeType.USER, user.id),
                type=NodeType.USER,
                label=user.name,
                reference=f"/users/{user.id}",
                properties={
                    "source_id": user.id,
                    "email": user.email,
                    "department": user.department,
                    "active": user.active,
                    "operator_role": user.operator_role,
                },
            )
        )

    for group in db.scalars(select(Group).order_by(Group.id)).all():
        graph.add_node(
            GraphNode(
                id=graph_node_id(NodeType.GROUP, group.id),
                type=NodeType.GROUP,
                label=group.display_name,
                reference=f"/scim/v2/Groups/{group.id}",
                timestamp=group.created_at,
                properties={
                    "source_id": group.id,
                    "display_name": group.display_name,
                    "updated_at": group.updated_at,
                },
            )
        )

    for profile in db.scalars(
        select(EnterpriseUserProfile).order_by(EnterpriseUserProfile.id)
    ).all():
        graph.add_node(
            GraphNode(
                id=graph_node_id(NodeType.ENTERPRISE_PROFILE, profile.id),
                type=NodeType.ENTERPRISE_PROFILE,
                label=f"Enterprise profile {profile.id}",
                reference=f"/scim/v2/Users/{profile.user_id}",
                timestamp=profile.created_at,
                properties={
                    "source_id": profile.id,
                    "user_id": profile.user_id,
                    "employee_number": profile.employee_number,
                    "department": profile.department,
                    "division": profile.division,
                    "organization": profile.organization,
                    "cost_center": profile.cost_center,
                    "manager_id": profile.manager_id,
                    "updated_at": profile.updated_at,
                },
            )
        )


def _add_application_nodes(db: Session, graph: AuthorizationGraph) -> None:
    for application in db.scalars(select(Application).order_by(Application.id)).all():
        graph.add_node(
            GraphNode(
                id=graph_node_id(NodeType.APPLICATION, application.id),
                type=NodeType.APPLICATION,
                label=application.name,
                reference=f"/applications/{application.id}",
                properties={
                    "source_id": application.id,
                    "slug": application.slug,
                },
            )
        )

    for entitlement in db.scalars(select(Entitlement).order_by(Entitlement.id)).all():
        graph.add_node(
            GraphNode(
                id=graph_node_id(NodeType.ENTITLEMENT, entitlement.id),
                type=NodeType.ENTITLEMENT,
                label=entitlement.name,
                reference=f"/applications/{entitlement.application_id}/entitlements",
                properties={
                    "source_id": entitlement.id,
                    "slug": entitlement.slug,
                    "application_id": entitlement.application_id,
                },
            )
        )


def _add_connector_nodes(
    graph: AuthorizationGraph,
    registry: ConnectorRegistry,
) -> None:
    for connector in registry.list():
        graph.add_node(
            GraphNode(
                id=graph_node_id(NodeType.CONNECTOR, connector.name),
                type=NodeType.CONNECTOR,
                label=connector.display_name,
                reference=f"/connectors/{connector.name}",
                properties={
                    "source_id": connector.name,
                    "enabled": connector.enabled,
                    "supported_operations": [
                        operation.value for operation in connector.supported_operations
                    ],
                },
            )
        )


def _add_governance_nodes(db: Session, graph: AuthorizationGraph) -> None:
    for campaign in db.scalars(
        select(CertificationCampaign).order_by(CertificationCampaign.id)
    ).all():
        graph.add_node(
            GraphNode(
                id=graph_node_id(NodeType.CERTIFICATION_CAMPAIGN, campaign.id),
                type=NodeType.CERTIFICATION_CAMPAIGN,
                label=campaign.name,
                reference=f"/access-reviews/campaigns/{campaign.id}",
                timestamp=campaign.created_at,
                properties={
                    "source_id": campaign.id,
                    "status": campaign.status,
                    "created_by": campaign.created_by,
                    "default_reviewer_id": campaign.default_reviewer_id,
                    "total_items": campaign.total_items,
                    "completed_items": campaign.completed_items,
                    "approval_count": campaign.approval_count,
                    "revocation_count": campaign.revocation_count,
                    "abstain_count": campaign.abstain_count,
                },
            )
        )

    for item in db.scalars(
        select(CertificationReviewItem).order_by(CertificationReviewItem.id)
    ).all():
        graph.add_node(
            GraphNode(
                id=graph_node_id(NodeType.REVIEW_ITEM, item.id),
                type=NodeType.REVIEW_ITEM,
                label=f"Review item {item.id}",
                reference=f"/access-reviews/items/{item.id}",
                timestamp=item.created_at,
                properties={
                    "source_id": item.id,
                    "campaign_id": item.campaign_id,
                    "access_assignment_id": item.access_assignment_id,
                    "user_id": item.user_id,
                    "application_id": item.application_id,
                    "entitlement_id": item.entitlement_id,
                    "group_id": item.group_id,
                    "reviewer_id": item.reviewer_id,
                    "status": item.status,
                    "reviewed_at": item.reviewed_at,
                },
            )
        )


def _add_operations_nodes(db: Session, graph: AuthorizationGraph) -> None:
    for assignment in db.scalars(
        select(DelegationAssignment).order_by(DelegationAssignment.id)
    ).all():
        graph.add_node(
            GraphNode(
                id=graph_node_id(NodeType.DELEGATION, assignment.id),
                type=NodeType.DELEGATION,
                label=f"{assignment.delegation_role} delegation",
                reference=f"/delegation/assignments/{assignment.id}",
                timestamp=assignment.created_at,
                properties={
                    "source_id": assignment.id,
                    "delegate_user_id": assignment.delegate_user_id,
                    "scope_type": assignment.scope_type,
                    "scope_id": assignment.scope_id,
                    "delegation_role": assignment.delegation_role,
                    "created_by": assignment.created_by,
                    "expires_at": assignment.expires_at,
                    "active": assignment.active,
                },
            )
        )

    for job in db.scalars(select(ProvisioningJob).order_by(ProvisioningJob.id)).all():
        graph.add_node(
            GraphNode(
                id=graph_node_id(NodeType.PROVISIONING_JOB, job.id),
                type=NodeType.PROVISIONING_JOB,
                label=f"{job.connector} {job.operation}",
                reference=f"/provisioning/jobs/{job.id}",
                timestamp=job.created_at,
                properties={
                    "source_id": job.id,
                    "correlation_id": job.correlation_id,
                    "connector": job.connector,
                    "operation": job.operation,
                    "target_type": job.target_type,
                    "target_id": job.target_id,
                    "status": job.status,
                    "attempt_count": job.attempt_count,
                    "retry_count": job.retry_count,
                    "completed_at": job.completed_at,
                },
            )
        )

    for history in db.scalars(
        select(ProvisioningHistory).order_by(ProvisioningHistory.id)
    ).all():
        graph.add_node(
            GraphNode(
                id=graph_node_id(NodeType.PROVISIONING_HISTORY, history.id),
                type=NodeType.PROVISIONING_HISTORY,
                label=f"{history.event_type} {history.status}",
                reference=f"/provisioning/history?correlation_id={history.correlation_id}",
                timestamp=history.created_at,
                properties={
                    "source_id": history.id,
                    "job_id": history.job_id,
                    "correlation_id": history.correlation_id,
                    "connector": history.connector,
                    "operation": history.operation,
                    "event_type": history.event_type,
                    "status": history.status,
                    "message": history.message,
                    "attempt": history.attempt,
                },
            )
        )

    for job in db.scalars(select(RemediationJob).order_by(RemediationJob.id)).all():
        graph.add_node(
            GraphNode(
                id=graph_node_id(NodeType.REMEDIATION_JOB, job.id),
                type=NodeType.REMEDIATION_JOB,
                label=f"Remediation job {job.id}",
                reference=f"/remediation/jobs/{job.id}",
                timestamp=job.created_at,
                properties={
                    "source_id": job.id,
                    "campaign_id": job.campaign_id,
                    "review_item_id": job.review_item_id,
                    "provisioning_job_id": job.provisioning_job_id,
                    "correlation_id": job.correlation_id,
                    "remediation_type": job.remediation_type,
                    "status": job.status,
                    "initiated_by": job.initiated_by,
                },
            )
        )

    for event in db.scalars(select(AuditEvent).order_by(AuditEvent.id)).all():
        graph.add_node(
            GraphNode(
                id=graph_node_id(NodeType.AUDIT_EVENT, event.id),
                type=NodeType.AUDIT_EVENT,
                label=f"{event.action} {event.result}",
                reference=f"/audit-events?correlation_id={event.correlation_id or ''}",
                timestamp=event.created_at,
                properties={
                    "source_id": event.id,
                    "requester_id": event.requester_id,
                    "target_user_id": event.target_user_id,
                    "action": event.action,
                    "application_id": event.application_id,
                    "entitlement_id": event.entitlement_id,
                    "result": event.result,
                    "reason": event.reason,
                    "correlation_id": event.correlation_id,
                },
            )
        )


def _add_relationship_edges(db: Session, graph: AuthorizationGraph) -> None:
    for entitlement in db.scalars(select(Entitlement).order_by(Entitlement.id)).all():
        _add_edge_if_nodes_exist(
            graph,
            source=graph_node_id(NodeType.ENTITLEMENT, entitlement.id),
            target=graph_node_id(NodeType.APPLICATION, entitlement.application_id),
            edge_type=EdgeType.GRANTS_ACCESS_TO,
            label="Entitlement belongs to application",
            reference=f"/applications/{entitlement.application_id}/entitlements",
            properties={"entitlement_id": entitlement.id},
        )

    for membership in db.scalars(select(GroupMember).order_by(GroupMember.id)).all():
        _add_edge_if_nodes_exist(
            graph,
            source=graph_node_id(NodeType.USER, membership.user_id),
            target=graph_node_id(NodeType.GROUP, membership.group_id),
            edge_type=EdgeType.MEMBER_OF,
            label="User is member of group",
            reference=f"/scim/v2/Groups/{membership.group_id}",
            timestamp=membership.created_at,
            properties={"membership_id": membership.id},
        )

    for assignment in db.scalars(
        select(AccessAssignment).order_by(AccessAssignment.id)
    ).all():
        _add_edge_if_nodes_exist(
            graph,
            source=graph_node_id(NodeType.USER, assignment.user_id),
            target=graph_node_id(NodeType.ENTITLEMENT, assignment.entitlement_id),
            edge_type=EdgeType.HAS_ENTITLEMENT,
            label="User has entitlement",
            reference=f"/users/{assignment.user_id}/access",
            timestamp=assignment.granted_at,
            properties={"access_assignment_id": assignment.id},
        )

    for profile in db.scalars(
        select(EnterpriseUserProfile).order_by(EnterpriseUserProfile.id)
    ).all():
        _add_edge_if_nodes_exist(
            graph,
            source=graph_node_id(NodeType.USER, profile.user_id),
            target=graph_node_id(NodeType.ENTERPRISE_PROFILE, profile.id),
            edge_type=EdgeType.CONNECTED_TO,
            label="User has enterprise profile",
            reference=f"/scim/v2/Users/{profile.user_id}",
            timestamp=profile.created_at,
        )
        if profile.manager_id is not None:
            _add_edge_if_nodes_exist(
                graph,
                source=graph_node_id(NodeType.USER, profile.user_id),
                target=graph_node_id(NodeType.USER, profile.manager_id),
                edge_type=EdgeType.MANAGED_BY,
                label="User is managed by user",
                reference=f"/scim/v2/Users/{profile.user_id}",
                timestamp=profile.updated_at,
                properties={"enterprise_profile_id": profile.id},
            )

    _add_delegation_edges(db, graph)
    _add_governance_edges(db, graph)
    _add_provisioning_edges(db, graph)
    _add_remediation_edges(db, graph)
    _add_audit_edges(db, graph)


def _add_delegation_edges(db: Session, graph: AuthorizationGraph) -> None:
    for assignment in db.scalars(
        select(DelegationAssignment).order_by(DelegationAssignment.id)
    ).all():
        delegation_id = graph_node_id(NodeType.DELEGATION, assignment.id)
        _add_edge_if_nodes_exist(
            graph,
            source=graph_node_id(NodeType.USER, assignment.delegate_user_id),
            target=delegation_id,
            edge_type=EdgeType.DELEGATED_TO,
            label="User has delegated administration assignment",
            reference=f"/delegation/assignments/{assignment.id}",
            timestamp=assignment.created_at,
        )
        _add_edge_if_nodes_exist(
            graph,
            source=graph_node_id(NodeType.USER, assignment.created_by),
            target=delegation_id,
            edge_type=EdgeType.AUDITED_BY,
            label="User created delegation assignment",
            reference=f"/delegation/assignments/{assignment.id}",
            timestamp=assignment.created_at,
        )
        scope_target = _delegation_scope_node_id(
            assignment.scope_type, assignment.scope_id
        )
        if scope_target is not None:
            _add_edge_if_nodes_exist(
                graph,
                source=delegation_id,
                target=scope_target,
                edge_type=EdgeType.CONNECTED_TO,
                label="Delegation applies to scope",
                reference=f"/delegation/assignments/{assignment.id}",
                timestamp=assignment.created_at,
                properties={"scope_type": assignment.scope_type},
            )


def _add_governance_edges(db: Session, graph: AuthorizationGraph) -> None:
    for campaign in db.scalars(
        select(CertificationCampaign).order_by(CertificationCampaign.id)
    ).all():
        campaign_id = graph_node_id(NodeType.CERTIFICATION_CAMPAIGN, campaign.id)
        for user_id, label in (
            (campaign.created_by, "User created certification campaign"),
            (campaign.default_reviewer_id, "User is default campaign reviewer"),
        ):
            _add_edge_if_nodes_exist(
                graph,
                source=graph_node_id(NodeType.USER, user_id),
                target=campaign_id,
                edge_type=EdgeType.REVIEWED_IN,
                label=label,
                reference=f"/access-reviews/campaigns/{campaign.id}",
                timestamp=campaign.created_at,
            )

    for item in db.scalars(
        select(CertificationReviewItem).order_by(CertificationReviewItem.id)
    ).all():
        item_id = graph_node_id(NodeType.REVIEW_ITEM, item.id)
        _add_edge_if_nodes_exist(
            graph,
            source=item_id,
            target=graph_node_id(NodeType.CERTIFICATION_CAMPAIGN, item.campaign_id),
            edge_type=EdgeType.REVIEWED_IN,
            label="Review item belongs to campaign",
            reference=f"/access-reviews/campaigns/{item.campaign_id}/items",
            timestamp=item.created_at,
        )
        for node_type, source_id, label in (
            (NodeType.USER, item.user_id, "User access reviewed in item"),
            (NodeType.USER, item.reviewer_id, "Reviewer assigned to item"),
            (NodeType.APPLICATION, item.application_id, "Application reviewed in item"),
            (NodeType.ENTITLEMENT, item.entitlement_id, "Entitlement reviewed in item"),
        ):
            _add_edge_if_nodes_exist(
                graph,
                source=graph_node_id(node_type, source_id),
                target=item_id,
                edge_type=EdgeType.REVIEWED_IN,
                label=label,
                reference=f"/access-reviews/items/{item.id}",
                timestamp=item.created_at,
            )
        if item.group_id is not None:
            _add_edge_if_nodes_exist(
                graph,
                source=graph_node_id(NodeType.GROUP, item.group_id),
                target=item_id,
                edge_type=EdgeType.REVIEWED_IN,
                label="Group reviewed in item",
                reference=f"/access-reviews/items/{item.id}",
                timestamp=item.created_at,
            )


def _add_provisioning_edges(db: Session, graph: AuthorizationGraph) -> None:
    for job in db.scalars(select(ProvisioningJob).order_by(ProvisioningJob.id)).all():
        job_id = graph_node_id(NodeType.PROVISIONING_JOB, job.id)
        _add_edge_if_nodes_exist(
            graph,
            source=job_id,
            target=graph_node_id(NodeType.CONNECTOR, job.connector),
            edge_type=EdgeType.CONNECTED_TO,
            label="Provisioning job executed through connector",
            reference=f"/provisioning/jobs/{job.id}",
            timestamp=job.created_at,
            correlation_id=job.correlation_id,
        )
        target_node = _provisioning_target_node_id(job.target_type, job.target_id)
        if target_node is not None:
            _add_edge_if_nodes_exist(
                graph,
                source=target_node,
                target=job_id,
                edge_type=EdgeType.PROVISIONED_BY,
                label="Target provisioned by job",
                reference=f"/provisioning/jobs/{job.id}",
                timestamp=job.created_at,
                correlation_id=job.correlation_id,
            )

    for history in db.scalars(
        select(ProvisioningHistory).order_by(ProvisioningHistory.id)
    ).all():
        _add_edge_if_nodes_exist(
            graph,
            source=graph_node_id(NodeType.PROVISIONING_HISTORY, history.id),
            target=graph_node_id(NodeType.PROVISIONING_JOB, history.job_id),
            edge_type=EdgeType.PROVISIONED_BY,
            label="Provisioning history belongs to job",
            reference=f"/provisioning/history?correlation_id={history.correlation_id}",
            timestamp=history.created_at,
            correlation_id=history.correlation_id,
        )


def _add_remediation_edges(db: Session, graph: AuthorizationGraph) -> None:
    for job in db.scalars(select(RemediationJob).order_by(RemediationJob.id)).all():
        remediation_id = graph_node_id(NodeType.REMEDIATION_JOB, job.id)
        _add_edge_if_nodes_exist(
            graph,
            source=graph_node_id(NodeType.REVIEW_ITEM, job.review_item_id),
            target=remediation_id,
            edge_type=EdgeType.REMEDIATED_BY,
            label="Review item remediated by job",
            reference=f"/remediation/jobs/{job.id}",
            timestamp=job.created_at,
            correlation_id=job.correlation_id,
        )
        _add_edge_if_nodes_exist(
            graph,
            source=remediation_id,
            target=graph_node_id(NodeType.CERTIFICATION_CAMPAIGN, job.campaign_id),
            edge_type=EdgeType.REMEDIATED_BY,
            label="Remediation belongs to campaign",
            reference=f"/remediation/jobs/{job.id}",
            timestamp=job.created_at,
            correlation_id=job.correlation_id,
        )
        _add_edge_if_nodes_exist(
            graph,
            source=graph_node_id(NodeType.USER, job.initiated_by),
            target=remediation_id,
            edge_type=EdgeType.AUDITED_BY,
            label="User initiated remediation",
            reference=f"/remediation/jobs/{job.id}",
            timestamp=job.created_at,
            correlation_id=job.correlation_id,
        )
        if job.provisioning_job_id is not None:
            _add_edge_if_nodes_exist(
                graph,
                source=remediation_id,
                target=graph_node_id(
                    NodeType.PROVISIONING_JOB, job.provisioning_job_id
                ),
                edge_type=EdgeType.PROVISIONED_BY,
                label="Remediation executed by provisioning job",
                reference=f"/remediation/jobs/{job.id}",
                timestamp=job.created_at,
                correlation_id=job.correlation_id,
            )


def _add_audit_edges(db: Session, graph: AuthorizationGraph) -> None:
    for event in db.scalars(select(AuditEvent).order_by(AuditEvent.id)).all():
        event_id = graph_node_id(NodeType.AUDIT_EVENT, event.id)
        for source, label in (
            (
                graph_node_id(NodeType.USER, event.requester_id),
                "Requester audited by event",
            ),
            (
                graph_node_id(NodeType.USER, event.target_user_id),
                "Target user audited by event",
            ),
            (
                graph_node_id(NodeType.APPLICATION, event.application_id),
                "Application audited by event",
            ),
            (
                graph_node_id(NodeType.ENTITLEMENT, event.entitlement_id),
                "Entitlement audited by event",
            ),
        ):
            _add_edge_if_nodes_exist(
                graph,
                source=source,
                target=event_id,
                edge_type=EdgeType.AUDITED_BY,
                label=label,
                reference=f"/audit-events?correlation_id={event.correlation_id or ''}",
                timestamp=event.created_at,
                correlation_id=event.correlation_id,
                properties={"audit_event_id": event.id, "action": event.action},
            )


def _add_edge_if_nodes_exist(
    graph: AuthorizationGraph,
    *,
    source: str,
    target: str,
    edge_type: EdgeType,
    label: str,
    reference: str,
    properties: dict[str, Any] | None = None,
    timestamp=None,
    correlation_id: str | None = None,
) -> None:
    if source not in graph.nodes or target not in graph.nodes:
        return

    graph.add_edge(
        source=source,
        target=target,
        edge_type=edge_type,
        label=label,
        reference=reference,
        properties=properties,
        timestamp=timestamp,
        correlation_id=correlation_id,
    )


def _delegation_scope_node_id(scope_type: str, scope_id: int) -> str | None:
    scope = scope_type.upper()
    if scope == "APPLICATION":
        return graph_node_id(NodeType.APPLICATION, scope_id)
    if scope == "GROUP":
        return graph_node_id(NodeType.GROUP, scope_id)
    if scope == "ENTITLEMENT":
        return graph_node_id(NodeType.ENTITLEMENT, scope_id)
    return None


def _provisioning_target_node_id(
    target_type: str,
    target_id: str | None,
) -> str | None:
    if target_id is None:
        return None

    normalized_type = target_type.lower()
    if normalized_type == "user":
        return graph_node_id(NodeType.USER, target_id)
    if normalized_type == "group":
        return graph_node_id(NodeType.GROUP, target_id)
    if normalized_type == "entitlement":
        return graph_node_id(NodeType.USER, target_id)
    return None
