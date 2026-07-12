# AccessIQ Architecture

AccessIQ is a FastAPI IAM learning platform that models authentication, API RBAC, deterministic access policy, audit logging, and SCIM provisioning. The system is intentionally modular so future connector delivery, access reviews, and AI explanations can be added without rewriting the core API.

## System Overview

```mermaid
flowchart LR
    IdP["Enterprise IdP"] --> SCIM["SCIM API"]
    User["API Caller"] --> REST["REST API"]
    SCIM --> Auth["JWT Authentication"]
    REST --> Auth
    Auth --> RBAC["API RBAC"]
    RBAC --> Services["Service Layer"]
    Services --> Policy["Business Policy Engine"]
    Services --> Audit["Audit Logging"]
    Services --> Events["Domain Events"]
    Events --> Orchestrator["Provisioning Orchestrator"]
    Orchestrator --> Jobs["Provisioning Jobs"]
    Orchestrator --> Registry["Connector Registry"]
    Registry --> Connectors["Connector Implementations"]
    Jobs --> DB
    Audit --> DB["Database"]
    Services --> DB
```

## Layered Architecture

AccessIQ keeps request handling, validation, business logic, audit, and persistence separated.

```mermaid
flowchart TD
    Route["FastAPI route"]
    Validation["Protocol validation"]
    Service["Service layer"]
    Policy["Policy engine"]
    Audit["Audit event"]
    Events["In-process domain events"]
    Orchestrator["Provisioning orchestrator"]
    Jobs["Provisioning jobs and history"]
    Registry["Connector registry"]
    Connectors["Connector implementations"]
    Database["SQLAlchemy models"]

    Route --> Validation
    Validation --> Service
    Service --> Policy
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

RBAC decides whether a caller may invoke an endpoint. It does not decide whether an access grant is appropriate. Business policy decisions are separate.

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
- timestamp

## Service Layer

Reusable services own mutation logic:

- `UserService`: user creation, replacement, patching, deactivation, duplicate userName checks.
- `GroupService`: group creation, replacement, patching, membership validation.
- `EnterpriseUserService`: enterprise profile mutation, employeeNumber uniqueness, manager validation, cycle prevention.
- `ProvisioningJobService`: provisioning job lifecycle, immutable history, retry tracking, and query filtering.

Services do not know FastAPI request objects. SCIM provisioning helpers translate protocol payloads and service errors into SCIM responses.

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

## Future AI Explanation Architecture

Future AI explanation work should consume deterministic system context rather than replace policy decisions.

```mermaid
flowchart TD
    Decision["Policy or provisioning decision"]
    Context["Structured audit and policy context"]
    Explanation["Future AI explanation service"]
    UserFacing["Human-readable explanation"]

    Decision --> Context
    Context --> Explanation
    Explanation --> UserFacing
```

The policy engine remains deterministic and authoritative.
