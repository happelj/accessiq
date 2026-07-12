# Access Reviews And Certification Campaigns

Milestone 8A adds the governance foundation for AccessIQ. Access reviews are the certification workflow used by Identity Governance & Administration platforms to periodically ask reviewers whether users should keep access.

This layer records decisions only. It does not revoke access, run connectors, schedule jobs, or perform background remediation.

## IGA Concepts

An access review campaign is a governance exercise over current access. A reviewer certifies each review item with one of three decisions:

- `APPROVE`: access is still appropriate.
- `REVOKE`: access should be removed by a future remediation workflow.
- `ABSTAIN`: reviewer cannot certify or revoke the access.

```mermaid
flowchart TD
    Access["Current access assignments"]
    Campaign["CertificationCampaign"]
    Items["CertificationReviewItem"]
    Decision["CertificationDecision"]
    Remediation["Future remediation"]

    Access --> Campaign
    Campaign --> Items
    Items --> Decision
    Decision -. "future milestone" .-> Remediation
```

## Data Model

`CertificationCampaign` stores lifecycle and summary state:

- name and description
- status
- creator
- default reviewer
- timestamps for create/start/complete/cancel
- total item count
- completed item count
- approval, revocation, and abstain counts

`CertificationReviewItem` stores one access decision target:

- campaign
- access assignment
- user
- application
- entitlement
- optional group
- reviewer
- status
- reviewed timestamp

`CertificationDecision` stores the current decision for a review item:

- review item
- campaign
- reviewer
- decision
- comments
- create/update timestamps

The schema is normalized. No review item or decision payload is stored as a JSON blob.

## Campaign Lifecycle

```mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> ACTIVE: start campaign
    DRAFT --> CANCELLED: cancel campaign
    ACTIVE --> COMPLETED: all review items decided
    ACTIVE --> CANCELLED: cancel campaign
    COMPLETED --> [*]
    CANCELLED --> [*]
```

Invalid transitions are rejected. Completed and cancelled campaigns no longer accept decisions.

## Review Generation

Starting a draft campaign snapshots current access assignments into review items.

```mermaid
sequenceDiagram
    participant Admin
    participant API
    participant Campaigns as CampaignService
    participant DB

    Admin->>API: POST /access-reviews/campaigns/{id}/start
    API->>Campaigns: start_campaign()
    Campaigns->>DB: read current AccessAssignment rows
    Campaigns->>DB: create CertificationReviewItem rows
    Campaigns->>DB: mark campaign ACTIVE
    Campaigns-->>API: active campaign summary
    API-->>Admin: 200 OK
```

Each generated item references the user, application, entitlement, access assignment, and assigned reviewer.

## Reviewer Workflow

```mermaid
sequenceDiagram
    participant Reviewer
    participant API
    participant Reviews as ReviewService
    participant Audit
    participant Events

    Reviewer->>API: GET /access-reviews/campaigns/{id}/items
    API-->>Reviewer: pending review items
    Reviewer->>API: POST /access-reviews/items/{id}/decision
    API->>Reviews: record_decision(APPROVE/REVOKE/ABSTAIN)
    Reviews->>Audit: decision audit event
    Reviews->>Events: CertificationDecisionRecorded
    API-->>Reviewer: updated review item
```

Decision updates are supported while a campaign is active. Updating a decision recalculates campaign counts and publishes `CertificationDecisionUpdated`.

## APIs

Campaign endpoints:

- `POST /access-reviews/campaigns`
- `GET /access-reviews/campaigns`
- `GET /access-reviews/campaigns/{campaign_id}`
- `GET /access-reviews/campaigns/{campaign_id}/summary`
- `POST /access-reviews/campaigns/{campaign_id}/start`
- `POST /access-reviews/campaigns/{campaign_id}/cancel`
- `POST /access-reviews/campaigns/{campaign_id}/complete`

Review item endpoints:

- `GET /access-reviews/campaigns/{campaign_id}/items`
- `GET /access-reviews/items/{item_id}`
- `POST /access-reviews/items/{item_id}/decision`

Read endpoints require `security_admin`, `iam_admin`, or `auditor`. Campaign lifecycle mutations require `security_admin` or `iam_admin`. Decision recording allows `security_admin`, `iam_admin`, or `auditor`.

## Audit And Domain Events

Campaign lifecycle actions create audit events using the seeded `Governance` application and `Access Review Certification` entitlement. Decision audit events use the actual application and entitlement being reviewed.

Audit actions:

- `certification_campaign_created`
- `certification_campaign_started`
- `certification_campaign_cancelled`
- `certification_campaign_completed`
- `certification_review_approved`
- `certification_review_revoked`
- `certification_review_abstained`
- `certification_decision_updated`

Domain events:

- `CertificationCampaignCreated`
- `CertificationCampaignStarted`
- `CertificationCampaignCompleted`
- `CertificationCampaignCancelled`
- `CertificationDecisionRecorded`
- `CertificationDecisionUpdated`

## Future Remediation

Future remediation can consume `REVOKE` decisions after campaign completion:

```mermaid
flowchart LR
    Decisions["Completed REVOKE decisions"]
    Remediation["Future remediation service"]
    Jobs["ProvisioningJobService"]
    Orchestrator["ProvisioningOrchestrator"]
    Connector["IdentityConnector"]

    Decisions --> Remediation
    Remediation --> Jobs
    Remediation --> Orchestrator
    Orchestrator --> Connector
```

The current milestone intentionally stops before remediation. This keeps governance decisions reviewable and auditable before any access removal occurs.
