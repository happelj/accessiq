# AccessIQ Architecture

AccessIQ is a FastAPI IAM learning platform that models authentication, API RBAC, deterministic access policy, audit logging, SCIM provisioning, connector execution, provisioning history, access review governance, authorization graph traversal, deterministic AI context assembly, and grounded AI explanations. The system is intentionally modular so provider-backed explanations can be added without rewriting the core API.

## System Overview

```mermaid
flowchart LR
    IdP["Enterprise IdP"] --> SCIM["SCIM API"]
    User["API Caller"] --> REST["REST API"]
    SCIM --> Auth["JWT Authentication"]
    REST --> Auth
    Auth --> RBAC["API RBAC"]
    RBAC --> Delegation["Delegation Service"]
    RBAC --> Services["Service Layer"]
    Delegation --> Policy["Business Policy Engine"]
    Delegation --> Audit
    Delegation --> Events
    Services --> Governance["Governance Services"]
    Services --> Policy
    Services --> Audit["Audit Logging"]
    Services --> Events["Domain Events"]
    Governance --> Audit
    Governance --> Events
    Governance --> DB
    Governance --> Remediation["Remediation Engine"]
    Events --> Orchestrator["Provisioning Orchestrator"]
    Remediation --> Orchestrator
    Orchestrator --> Jobs["Provisioning Jobs"]
    Orchestrator --> Registry["Connector Registry"]
    Registry --> Connectors["Connector Implementations"]
    Jobs --> DB
    Audit --> DB["Database"]
    Services --> DB
    DB --> GraphBuilder["Graph Builder"]
    Connectors --> GraphBuilder
    GraphBuilder --> Graph["Authorization Graph"]
    Graph --> Query["Query Engine"]
    Query --> Evidence["Evidence Builder"]
    Evidence --> AIContext["AI Context Assembly"]
    AIContext --> Prompt["Structured Prompt"]
    Prompt --> Provider["LLM Provider"]
    Provider --> Grounded["Grounded Explanation"]
    Grounded --> REST
    Prompt --> REST
    Evidence --> REST
```

## Layered Architecture

AccessIQ keeps request handling, validation, business logic, audit, and persistence separated.

```mermaid
flowchart TD
    Route["FastAPI route"]
    Validation["Protocol validation"]
    Service["Service layer"]
    Governance["Governance services"]
    Delegation["Delegation service"]
    Policy["Policy engine"]
    Audit["Audit event"]
    Events["In-process domain events"]
    Orchestrator["Provisioning orchestrator"]
    Remediation["Remediation engine"]
    Jobs["Provisioning jobs and history"]
    Registry["Connector registry"]
    Connectors["Connector implementations"]
    Database["SQLAlchemy models"]

    Route --> Validation
    Validation --> Service
    Service --> Governance
    Service --> Delegation
    Delegation --> Policy
    Delegation --> Audit
    Delegation --> Events
    Service --> Policy
    Governance --> Remediation
    Service --> Audit
    Service --> Events
    Events --> Orchestrator
    Orchestrator --> Jobs
    Orchestrator --> Registry
    Registry --> Connectors
    Audit --> Database
    Service --> Database
```

Routes should stay thin. They authenticate, authorize, parse request context, and delegate to protocol or service helpers. Business rules belong in services or policy modules.

## Authorization Graph

Milestone 11A adds a deterministic read model under `app/graph`:

```mermaid
flowchart LR
    Database["Relational database"]
    Registry["Connector registry"]
    Builder["Graph Builder"]
    Cache["In-memory graph cache"]
    Graph["Authorization Graph"]
    Query["Query Engine"]
    Evidence["Evidence Builder"]
    Routes["Graph REST API"]
    Export["JSON / Mermaid / DOT Export"]

    Database --> Builder
    Registry --> Builder
    Builder --> Cache
    Cache --> Graph
    Graph --> Query
    Query --> Evidence
    Evidence --> Routes
    Graph --> Export
    Export --> Routes
```

The graph includes users, groups, applications, entitlements, delegations, certification campaigns, review items, provisioning jobs/history, remediation jobs, audit events, connectors, and enterprise profiles. It provides deterministic traversal and evidence for inspection, but it does not perform authorization decisions or replace the relational database.

## AI Context Assembly

Milestone 12A adds a deterministic AI preparation layer under `app/ai`:

```mermaid
flowchart LR
    Question["User Question"]
    Intent["Intent Classifier"]
    Query["Graph Query Engine"]
    Collect["Evidence Collection"]
    Rank["Evidence Ranking"]
    Budget["Token Budget"]
    Context["Context Assembly"]
    Prompt["Prompt Builder"]
    Routes["AI REST API"]
    Provider["LLM Provider"]
    Explanation["Grounded Explanation"]

    Question --> Intent
    Intent --> Query
    Query --> Collect
    Collect --> Rank
    Rank --> Budget
    Budget --> Context
    Context --> Prompt
    Prompt --> Routes
    Prompt --> Provider
    Provider --> Explanation
    Explanation --> Routes
```

The AI context layer is read-only and deterministic. It uses explicit question parsing rules, graph queries, evidence normalization, duplicate removal, heuristic ranking, and approximate token budgeting. The explanation layer passes the structured prompt to a configured provider and returns a grounded answer with citations. Providers may explain evidence, but they do not make authorization, provisioning, review, remediation, governance, or policy decisions.

Provider adapters live under `app/ai/providers`. The mock provider is deterministic and no-network for tests. OpenAI and Anthropic adapters are optional and report unavailable when API keys are missing.

## Request Context

AccessIQ creates a per-request context in middleware before route execution. The context contains:

- `correlation_id`
- `request_start`
- `client_ip`
- `user_agent`
- `authenticated_user`

The API accepts caller-supplied `X-Correlation-ID` headers and generates one when omitted. The response always includes the resolved header. Authentication enriches the context with the loaded user, and audit/provisioning paths use the context correlation ID when a more specific operation ID is not supplied.

## Configuration And Dependencies

Environment access is centralized in `app/config.py`. The database, authentication, connector, and logging settings are exposed through cached providers. FastAPI dependencies in `app/dependencies.py` construct connector registries, orchestrators, provisioning services, governance services, remediation services, and delegation services. This keeps route modules from repeating construction logic while preserving service-level unit testability.

Repositories were not added during the architecture review because the existing service boundaries already own the useful query and mutation behavior. Adding repository wrappers around straightforward SQLAlchemy calls would add indirection without reducing current duplication.

## Observability

`app/observability.py` provides two lightweight primitives:

- structured JSON logging through the Python standard library
- an in-memory metrics registry exposed through health responses

Middleware records request counts, error counts, duration, method, path, status code, and correlation ID. User creation, audit, connector orchestration, review decisions, remediation jobs, and domain event publication increment focused counters.

## Health Model

`GET /health` returns a structured health report with:

- top-level `status`
- request `correlation_id`
- subsystem reports for database, connectors, audit, provisioning, domain events, and configuration
- metrics snapshot

The database subsystem remains critical. If the database probe fails, the endpoint returns `503`. Other subsystem details are included to make local and container validation easier without introducing a metrics stack.

## Authentication Flow

Users authenticate with `/login`. Passwords are verified using Argon2 through `passlib`, and successful login returns a signed JWT.

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant DB

    Client->>API: POST /login
    API->>DB: Load user by email
    DB-->>API: User
    API->>API: Verify password and sign JWT
    API-->>Client: Bearer token
```

## API RBAC

API RBAC uses the `operator_role` field on `User`. Protected endpoints call reusable FastAPI dependencies such as `require_roles("security_admin", "iam_admin")`.

RBAC decides whether a caller may invoke an endpoint or enter a delegated authorization path. It does not decide whether an access grant is appropriate. Delegation and business policy decisions are separate.

## Delegation Service

Delegated administration is isolated under `app/delegation`. It stores scoped authority in normalized `DelegationAssignment` records and evaluates whether a non-global operator can administer a specific application, group, or entitlement.

```mermaid
sequenceDiagram
    participant Operator
    participant API
    participant RBAC
    participant Delegation as DelegationService
    participant Policy as BusinessPolicy
    participant Audit

    Operator->>API: POST /access/grant
    API->>RBAC: Validate JWT and operator role
    RBAC-->>API: Authenticated user
    API->>Delegation: authorize_access_action()
    Delegation->>Audit: delegated_action_allowed/denied
    Delegation-->>API: effective delegation
    API->>Policy: evaluate grant/revoke policy
    Policy-->>API: allow or deny
```

Global `security_admin` and `iam_admin` users continue through the existing authorization path. Scoped delegates must have an active, unexpired assignment matching the entitlement or its parent application. Delegation never skips the business policy engine.

## Business Policy Engine

The policy engine evaluates access grant and revoke requests after API RBAC succeeds. Current policies cover inactive users, requester eligibility, finance restrictions, and administrator entitlement rules.

This keeps endpoint authorization distinct from entitlement policy.

## Audit Logging

Audit events are persisted in the same transaction as the operation they describe. If audit logging fails during provisioning, the database mutation rolls back and the API returns a SCIM-shaped server error for SCIM requests.

Audit events store:

- requester
- target user
- action
- application
- entitlement
- result
- reason
- correlation ID
- timestamp

When a route does not pass an explicit correlation ID, audit logging falls back to the request context correlation ID.

## Service Layer

Reusable services own mutation logic:

- `UserService`: user creation, replacement, patching, deactivation, duplicate userName checks.
- `GroupService`: group creation, replacement, patching, membership validation.
- `EnterpriseUserService`: enterprise profile mutation, employeeNumber uniqueness, manager validation, cycle prevention.
- `ProvisioningJobService`: provisioning job lifecycle, immutable history, retry tracking, and query filtering.
- `CampaignService`: certification campaign lifecycle, item generation, summary counts, and governance audit events.
- `ReviewService`: review item lookup, decision recording, decision updates, and decision audit events.
- `RemediationService`: governance-driven remediation jobs, campaign validation, duplicate prevention, connector execution, and provisioning job linkage.
- `DelegationService`: delegated administration assignments, scope validation, effective delegation lookup, delegated action authorization, and delegation audit/domain events.

Services do not know FastAPI request objects. SCIM provisioning helpers translate protocol payloads and service errors into SCIM responses.

## Governance Services

Access reviews are isolated under `app/governance`. The governance layer records certification decisions and prepares data for future remediation. It does not revoke access, call connectors, or run background work.

```mermaid
flowchart TD
    Route["Access review routes"]
    Campaigns["CampaignService"]
    Reviews["ReviewService"]
    Assignments["Current access assignments"]
    Items["CertificationReviewItem"]
    Decisions["CertificationDecision"]
    Audit["Audit events"]
    Events["Certification domain events"]

    Route --> Campaigns
    Route --> Reviews
    Campaigns --> Assignments
    Campaigns --> Items
    Reviews --> Decisions
    Campaigns --> Audit
    Reviews --> Audit
    Campaigns --> Events
    Reviews --> Events
```

Campaign statuses are `DRAFT`, `ACTIVE`, `COMPLETED`, and `CANCELLED`. Starting a campaign generates one review item for each active access assignment at that time. Review decisions can be `APPROVE`, `REVOKE`, or `ABSTAIN`; revoke decisions are retained for later remediation.

```mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> ACTIVE: start
    DRAFT --> CANCELLED: cancel
    ACTIVE --> COMPLETED: all items decided
    ACTIVE --> CANCELLED: cancel
    COMPLETED --> [*]
    CANCELLED --> [*]
```

## Remediation Engine

Remediation is isolated under `app/remediation`. It consumes completed access review campaigns and turns `REVOKE` decisions into provisioning-backed jobs.

```mermaid
sequenceDiagram
    participant Admin
    participant API
    participant Remediation as RemediationService
    participant Orchestrator as ProvisioningOrchestrator
    participant Jobs as ProvisioningJobService
    participant Connector

    Admin->>API: POST /access-reviews/campaigns/{id}/remediate
    API->>Remediation: execute_campaign()
    Remediation->>Remediation: create RemediationJob
    Remediation->>Orchestrator: execute revoke_entitlement
    Orchestrator->>Jobs: create/start/complete ProvisioningJob
    Orchestrator->>Connector: revoke_entitlement
    Connector-->>Orchestrator: ConnectorResult
    Orchestrator-->>Remediation: result
    Remediation->>Remediation: link provisioning_job_id
    API-->>Admin: remediation job summary
```

Remediation jobs have statuses `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, and `SKIPPED`. The current execution path is synchronous and API-triggered; a future scheduler can execute pending jobs asynchronously without changing access review or connector contracts.

## Connector Framework

The connector framework is isolated under `app/connectors`. It provides production-style extension points for future outbound provisioning without integrating with external SaaS APIs in this milestone.

```mermaid
flowchart TD
    Request["Domain event or service request"]
    Orchestrator["ProvisioningOrchestrator"]
    Retry["RetryPolicy"]
    Jobs["ProvisioningJobService"]
    Registry["ConnectorRegistry"]
    Connector["IdentityConnector"]
    Result["ConnectorResult"]
    Audit["Audit event"]
    Events["Connector domain events"]

    Request --> Orchestrator
    Orchestrator --> Retry
    Orchestrator --> Jobs
    Orchestrator --> Registry
    Registry --> Connector
    Connector --> Result
    Result --> Orchestrator
    Orchestrator --> Audit
    Orchestrator --> Events
```

Current mock connector implementations are deterministic:

- Salesforce
- GitHub
- Zendesk
- Finance

They implement user lifecycle, group lifecycle, group membership, entitlement grant/revoke, and health check operations. Simulation modes cover success, validation failure, timeout, rate limiting, retryable failure, non-retryable failure, degraded health, and unavailable health.

## Provisioning Job Engine

The provisioning job engine persists connector execution state without introducing asynchronous processing.

```mermaid
sequenceDiagram
    participant Orchestrator
    participant Jobs as ProvisioningJobService
    participant Connector
    participant History as ProvisioningHistory
    participant Audit
    participant Events

    Orchestrator->>Jobs: create_job(correlation_id)
    Jobs->>History: job_created
    Orchestrator->>Jobs: start_job(attempt)
    Jobs->>History: job_started
    Orchestrator->>Connector: execute operation
    Connector-->>Orchestrator: ConnectorResult or exception
    Orchestrator->>Jobs: complete_job/fail_job/record_retry
    Jobs->>History: immutable event entries
    Orchestrator->>Audit: correlation-aware audit events
    Jobs->>Events: job lifecycle domain events
```

`ProvisioningJob` is the current state record. `ProvisioningHistory` is append-only operational history. `AuditEvent.correlation_id` links job tracking to audit inspection.

## SCIM Architecture

SCIM is isolated under `app/scim`.

```mermaid
flowchart TD
    Routes["app/scim/routes.py"]
    Validation["SCIM validation and parsing"]
    Provisioning["SCIM provisioning helpers"]
    Services["User, Group, Enterprise services"]
    Audit["Audit service"]
    Publisher["Domain event publisher"]
    Models["SQLAlchemy models"]

    Routes --> Validation
    Validation --> Provisioning
    Provisioning --> Services
    Provisioning --> Audit
    Services --> Publisher
    Services --> Models
    Audit --> Models
```

Supported SCIM surfaces:

- ServiceProviderConfig
- ResourceTypes
- Schemas
- User read and provisioning
- Group read and provisioning
- Enterprise User Extension

SCIM errors use the `application/scim+json` media type and SCIM Error schema.

## Enterprise User Extension

Enterprise profile data is normalized in `EnterpriseUserProfile`.

```mermaid
erDiagram
    users ||--o| enterprise_user_profiles : "has"
    users ||--o{ enterprise_user_profiles : "manages"

    users {
        int id
        string email
        string name
        string department
        bool active
        string operator_role
    }

    enterprise_user_profiles {
        int id
        int user_id
        string employee_number
        string department
        string division
        string organization
        string cost_center
        int manager_id
    }
```

Manager assignments must reference existing users. The service rejects self-manager assignments and manager cycles.

## Domain Events

Domain events are in-process only. They provide a clean seam for future connector delivery without introducing asynchronous infrastructure now.

Current event families include:

- user provisioned
- group created/updated
- group membership added/removed/replaced
- enterprise profile created/updated
- enterprise attributes changed
- manager changed
- connector called/succeeded/failed
- connector retry scheduled
- provisioning started/completed/failed
- provisioning job created/started/completed/failed
- provisioning retry recorded
- certification campaign created/started/completed/cancelled
- certification decision recorded/updated
- remediation created/started/completed/failed
- delegation assigned/removed and delegated access allowed/denied

## Future Connector Architecture

Future connector delivery can subscribe to domain events and dispatch outbound changes to SaaS applications through the same connector interface and orchestrator.

```mermaid
flowchart LR
    Events["Domain events"] --> Queue["Future durable queue"]
    Queue --> Worker["Connector worker"]
    Worker --> Orchestrator["ProvisioningOrchestrator"]
    Orchestrator --> Jobs["ProvisioningJobService"]
    Orchestrator --> Registry["ConnectorRegistry"]
    Registry --> Connector["Real connector"]
    Connector --> SaaS["Downstream SaaS APIs"]
    Worker --> Audit["Delivery audit"]
```

The current implementation intentionally does not include the queue, worker, or real SaaS API calls.

## AI Explanation Architecture

AI explanations consume deterministic context and prompt objects produced by `app/ai` rather than replacing policy decisions.

```mermaid
flowchart TD
    Question["User question"]
    Context["AI context assembly"]
    Prompt["Structured prompt"]
    Provider["LLM provider"]
    UserFacing["Human-readable explanation"]
    Conversation["In-memory conversation"]

    Question --> Context
    Context --> Prompt
    Prompt --> Provider
    Provider --> UserFacing
    UserFacing --> Conversation
```

The policy engine, graph, provisioning services, reviews, and remediation services remain deterministic and authoritative.

## AWS Infrastructure Foundation

Milestone 15A adds an AWS Infrastructure as Code foundation under `infrastructure/terraform`. The Terraform layer is intentionally separate from application code and Helm runtime configuration.

```mermaid
flowchart TD
    Terraform["Terraform Environments"]
    Modules["Reusable Modules"]
    Network["VPC, Subnets, NAT"]
    EKS["EKS and Managed Nodes"]
    RDS["Private PostgreSQL RDS"]
    ECR["Backend and Frontend ECR"]
    IAM["IAM Roles and Policies"]
    Secrets["Secrets Manager"]
    Helm["Existing Helm Chart"]

    Terraform --> Modules
    Modules --> Network
    Modules --> EKS
    Modules --> RDS
    Modules --> ECR
    Modules --> IAM
    Modules --> Secrets
    Helm -. "future deployment milestone" .-> EKS
```

The AWS layer provisions infrastructure only. It does not deploy AccessIQ to EKS, push container images, or configure GitHub Actions deployment. Future deployment work can consume the Terraform outputs for cluster name, subnet IDs, ECR repository URLs, RDS endpoint, IAM role ARNs, and Secrets Manager ARNs while preserving the existing local Kubernetes workflow.
