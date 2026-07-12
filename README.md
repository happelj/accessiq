# AccessIQ

Initial FastAPI service scaffold for AccessIQ.

## Local Development

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the API:

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.

## Docker

Copy the example environment file if you want local overrides:

```bash
cp .env.example .env
```

Start the API and PostgreSQL:

```bash
docker compose up --build
```

## Documentation

- [Architecture](docs/architecture.md)
- [SCIM implementation](docs/scim.md)
- [Connector framework](docs/connectors.md)
- [Provisioning jobs and history](docs/provisioning.md)
- [Access reviews and certification campaigns](docs/access_reviews.md)

## Authentication And API Authorization

AccessIQ separates authentication, API authorization, business policy evaluation, and audit logging:

```text
JWT Authentication
  -> API RBAC
  -> Business Policy Engine
  -> Audit Logging
  -> Database
```

Authentication answers who the caller is. API RBAC decides whether that authenticated caller may invoke a REST endpoint. The business policy engine then evaluates the requested access change. These layers are intentionally separate so endpoint security does not leak into entitlement policy logic.

Passwords are hashed with Argon2 through `passlib`. Plaintext passwords are never stored or compared directly. Seed users receive development passwords during startup, and existing databases are upgraded safely by adding a `password_hash` column when it is missing.

JWT access tokens are signed locally and include standard `sub`, `iat`, and `exp` claims. The reusable `get_current_user()` dependency validates bearer tokens and loads the matching user.

### Configuration

Set these environment variables as needed:

- `JWT_SECRET`: signing secret for access tokens. Default is development-only.
- `JWT_ALGORITHM`: JWT signing algorithm. Default: `HS256`.
- `ACCESS_TOKEN_EXPIRE_MINUTES`: token lifetime in minutes. Default: `30`.
- `ENABLE_SALESFORCE_CONNECTOR`: enables the mock Salesforce connector. Default: `true`.
- `ENABLE_GITHUB_CONNECTOR`: enables the mock GitHub connector. Default: `true`.
- `ENABLE_ZENDESK_CONNECTOR`: enables the mock Zendesk connector. Default: `true`.
- `ENABLE_FINANCE_CONNECTOR`: enables the mock Finance connector. Default: `true`.
- `SALESFORCE_API_BASE_URL`, `GITHUB_API_BASE_URL`, `ZENDESK_API_BASE_URL`, `FINANCE_API_BASE_URL`: reserved for future real connector credentials and endpoints. Milestone 7A does not call external APIs.

### Login Example

```bash
curl -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"Password123!"}'
```

Response:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### Authenticated Request Example

```bash
curl -X POST http://localhost:8000/access/grant \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"target_user_id":2,"entitlement_id":1}'
```

### API RBAC

API authorization uses the `operator_role` field on the authenticated user. Role checks are implemented as reusable FastAPI dependencies, for example:

```python
Depends(require_roles("security_admin", "iam_admin"))
```

RBAC failures return `403 Insufficient privileges`. Missing, malformed, invalid, expired, or unknown bearer tokens return `401 Authentication required`.

Supported API roles:

- `security_admin`
- `iam_admin`
- `auditor`
- `helpdesk`
- `manager`
- `employee`

Legacy `administrator` and `help_desk` role values are still accepted as compatibility aliases.

| Endpoint | Required Role(s) |
| --- | --- |
| `POST /login` | Public |
| `GET /health` | Public |
| `GET /users` | Public |
| `GET /users/{user_id}` | Public |
| `POST /users` | Public |
| `GET /applications` | Public |
| `GET /applications/{application_id}/entitlements` | Public |
| `GET /users/{user_id}/access` | Public |
| `POST /access/grant` | `security_admin`, `iam_admin` |
| `POST /access/revoke` | `security_admin`, `iam_admin` |
| `GET /audit-events` | `security_admin`, `iam_admin`, `auditor` |
| `GET /connectors` | `security_admin`, `iam_admin`, `auditor` |
| `GET /connectors/{name}` | `security_admin`, `iam_admin`, `auditor` |
| `GET /connectors/{name}/health` | `security_admin`, `iam_admin`, `auditor` |
| `GET /provisioning/jobs` | `security_admin`, `iam_admin`, `auditor` |
| `GET /provisioning/jobs/{job_id}` | `security_admin`, `iam_admin`, `auditor` |
| `GET /provisioning/history` | `security_admin`, `iam_admin`, `auditor` |
| `POST /access-reviews/campaigns` | `security_admin`, `iam_admin` |
| `GET /access-reviews/campaigns` | `security_admin`, `iam_admin`, `auditor` |
| `GET /access-reviews/campaigns/{campaign_id}` | `security_admin`, `iam_admin`, `auditor` |
| `GET /access-reviews/campaigns/{campaign_id}/summary` | `security_admin`, `iam_admin`, `auditor` |
| `POST /access-reviews/campaigns/{campaign_id}/start` | `security_admin`, `iam_admin` |
| `POST /access-reviews/campaigns/{campaign_id}/cancel` | `security_admin`, `iam_admin` |
| `POST /access-reviews/campaigns/{campaign_id}/complete` | `security_admin`, `iam_admin` |
| `GET /access-reviews/campaigns/{campaign_id}/items` | `security_admin`, `iam_admin`, `auditor` |
| `GET /access-reviews/items/{item_id}` | `security_admin`, `iam_admin`, `auditor` |
| `POST /access-reviews/items/{item_id}/decision` | `security_admin`, `iam_admin`, `auditor` |

## SCIM 2.0 User And Group Provisioning

SCIM, the System for Cross-domain Identity Management, is the protocol enterprise identity providers use to automate identity lifecycle operations. Products such as Microsoft Entra ID, Okta, Ping Identity, Google Workspace, SailPoint, and OneLogin use SCIM to exchange user and group data with downstream applications.

AccessIQ implements SCIM 2.0 metadata endpoints, User read/provisioning operations, the Enterprise User Extension, and Group read/provisioning operations. It does not implement `DELETE /Users`, `DELETE /Groups`, or connector delivery yet. User deactivation is handled through `active=false` soft deactivation so inactive records remain visible to future provisioning calls.

```text
SCIM Route
  -> SCIM Validation
  -> SCIM Provisioning Layer
  -> User/Group/Enterprise Service
  -> Audit Logging
  -> Domain Events
  -> Database
```

The REST API remains the native AccessIQ API. The SCIM API is isolated under `app/scim`, and reusable user, group, and enterprise profile mutation logic lives under `app/services`. Future connector work can reuse these service and provisioning patterns without coupling to existing REST route handlers.

SCIM endpoints use the SCIM media type `application/scim+json`, return SCIM-shaped error payloads, and are protected with the existing JWT authentication and API RBAC layers. Dedicated SCIM bearer tokens can be added later without changing the SCIM metadata model.

| Endpoint | Status | Required Role(s) |
| --- | --- | --- |
| `GET /scim/v2/ServiceProviderConfig` | Implemented metadata | `security_admin`, `iam_admin` |
| `GET /scim/v2/ResourceTypes` | Implemented metadata | `security_admin`, `iam_admin` |
| `GET /scim/v2/Schemas` | Implemented metadata | `security_admin`, `iam_admin` |
| `GET /scim/v2/Users` | Implemented read operation | `security_admin`, `iam_admin` |
| `GET /scim/v2/Users/{id}` | Implemented read operation | `security_admin`, `iam_admin` |
| `POST /scim/v2/Users` | Implemented provisioning operation | `security_admin`, `iam_admin` |
| `PUT /scim/v2/Users/{id}` | Implemented provisioning operation | `security_admin`, `iam_admin` |
| `PATCH /scim/v2/Users/{id}` | Implemented provisioning operation | `security_admin`, `iam_admin` |
| `GET /scim/v2/Groups` | Implemented read operation | `security_admin`, `iam_admin` |
| `GET /scim/v2/Groups/{id}` | Implemented read operation | `security_admin`, `iam_admin` |
| `POST /scim/v2/Groups` | Implemented provisioning operation | `security_admin`, `iam_admin` |
| `PUT /scim/v2/Groups/{id}` | Implemented provisioning operation | `security_admin`, `iam_admin` |
| `PATCH /scim/v2/Groups/{id}` | Implemented provisioning operation | `security_admin`, `iam_admin` |

### SCIM User Resource

AccessIQ maps existing `User` rows into SCIM User resources:

- `id`: AccessIQ user ID serialized as a SCIM string ID.
- `userName`: user email address.
- `displayName`: AccessIQ display name.
- `name.formatted`: AccessIQ display name.
- `active`: AccessIQ active flag.
- `emails`: primary work email derived from the user email address.
- `urn:ietf:params:scim:schemas:extension:enterprise:2.0:User`: optional Enterprise User Extension data when present.
- `meta.resourceType`: `User`.
- `meta.location`: canonical SCIM resource URL.

`meta.lastModified` is omitted because AccessIQ does not yet store a user modification timestamp. Unsupported SCIM attributes are omitted rather than populated with placeholder values.

### SCIM User Provisioning

`POST /scim/v2/Users` creates a user from a SCIM User payload:

```json
{
  "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
  "userName": "new.user@example.com",
  "displayName": "New User",
  "active": true
}
```

Provisioning maps `userName` to the AccessIQ email field, `displayName` to the AccessIQ display name, and `active` to the soft-active flag. Provisioned users receive the default `employee` operator role and a generated password hash because SCIM provisioning does not authenticate users directly. If Enterprise User `department` is supplied, AccessIQ also keeps the internal user department aligned for policy evaluation; otherwise provisioned users receive the internal department value `SCIM Provisioned`.

`PUT /scim/v2/Users/{id}` performs full replacement of mutable SCIM User attributes while preserving the immutable AccessIQ user ID.

Duplicate `userName` values return SCIM `409 Conflict` with `scimType: uniqueness`.

Unknown users return SCIM `404`.

Invalid payloads, unsupported paths, malformed PATCH documents, and invalid data types return SCIM `400` errors.

### SCIM PATCH

`PATCH /scim/v2/Users/{id}` supports SCIM PatchOp documents:

```json
{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "replace",
      "path": "active",
      "value": false
    }
  ]
}
```

Supported operations:

- `replace`
- `add`
- `remove`

Supported paths:

- `userName`
- `displayName`
- `active`
- `employeeNumber`
- `department`
- `division`
- `organization`
- `costCenter`
- `manager`
- `urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:<attribute>`

`active=false` deactivates the user without deleting the row. `remove active` also deactivates the user. `userName` is required and cannot be removed.

### SCIM Enterprise User Extension

AccessIQ stores Enterprise User Extension data in a normalized `EnterpriseUserProfile` table rather than a JSON blob. Each user can have one enterprise profile.

Supported attributes:

- `employeeNumber`
- `department`
- `division`
- `organization`
- `costCenter`
- `manager`

Enterprise attributes are read and written under the RFC 7643 extension key:

```json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
  ],
  "userName": "new.user@example.com",
  "displayName": "New User",
  "active": true,
  "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
    "employeeNumber": "E-1001",
    "department": "Engineering",
    "division": "Platform",
    "organization": "AccessIQ",
    "costCenter": "ENG-001",
    "manager": {
      "value": "6"
    }
  }
}
```

Managers must reference existing AccessIQ users. AccessIQ rejects unknown managers, self-manager assignments, and circular manager chains with SCIM-shaped `400` validation errors. Manager responses use the SCIM Enterprise format:

```json
{
  "manager": {
    "value": "6",
    "$ref": "http://localhost:8000/scim/v2/Users/6",
    "displayName": "Maya Patel"
  }
}
```

`employeeNumber` is unique when present. Duplicate values return SCIM `409 Conflict` with `scimType: uniqueness`.

### SCIM Group Resource

AccessIQ maps normalized `Group` and `GroupMember` rows into SCIM Group resources:

- `id`: AccessIQ group ID serialized as a SCIM string ID.
- `displayName`: unique group display name.
- `members`: existing AccessIQ users referenced by user ID.
- `members[].value`: AccessIQ user ID serialized as a SCIM string ID.
- `members[].$ref`: canonical SCIM User resource URL.
- `members[].display`: user display name.
- `meta.resourceType`: `Group`.
- `meta.location`: canonical SCIM Group resource URL.
- `meta.lastModified`: group update timestamp.

### SCIM Group Provisioning

`POST /scim/v2/Groups` creates a group from a SCIM Group payload:

```json
{
  "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
  "displayName": "Finance Approvers",
  "members": [
    {
      "value": "1"
    }
  ]
}
```

`PUT /scim/v2/Groups/{id}` replaces the group `displayName` and membership set while preserving the immutable AccessIQ group ID.

Duplicate `displayName` values return SCIM `409 Conflict` with `scimType: uniqueness`.

Unknown groups return SCIM `404`.

Unknown member users, malformed member references, unsupported paths, malformed PATCH documents, and invalid data types return SCIM `400` errors.

### SCIM Group PATCH

`PATCH /scim/v2/Groups/{id}` supports SCIM PatchOp documents:

```json
{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "add",
      "path": "members",
      "value": [
        {
          "value": "1"
        }
      ]
    }
  ]
}
```

Supported operations:

- `replace`
- `add`
- `remove`

Supported paths:

- `displayName`
- `members`
- `members[value eq "123"]`

`add members` appends existing users, `remove members` clears all members, `remove members[value eq "123"]` removes one member, and `replace members` atomically replaces the normalized membership set.

### SCIM Provisioning Audit

Every SCIM provisioning action records an audit event through the existing audit system using the seeded `SCIM Provisioning` application and the `SCIM User Lifecycle`, `SCIM Enterprise User Extension`, or `SCIM Group Lifecycle` entitlement. Successful creates, updates, deactivations, enterprise profile changes, manager changes, group renames, and group membership changes use SCIM-specific audit actions. Duplicate conflicts, unknown users or groups, malformed PATCH requests, invalid payloads, and audit failures are handled with transaction rollback and SCIM-shaped errors.

SCIM provisioning also publishes lightweight in-process domain events for user provisioning, enterprise profile creation/update, manager and enterprise attribute changes, group creation, group updates, and group membership add/remove/replace operations. These events are intentionally local-only. Future workers can subscribe to these events and call the connector orchestrator without changing connector implementations.

### SCIM User Query Parameters

`GET /scim/v2/Users` returns a SCIM `ListResponse` with `schemas`, `totalResults`, `startIndex`, `itemsPerPage`, and `Resources`.

Pagination:

- `startIndex`: 1-based index of the first result. Default: `1`.
- `count`: maximum number of resources to return. Default: `100`.
- Out-of-range `startIndex` values return an empty `Resources` array with the requested `startIndex`.

Filters:

- `userName eq "alice@example.com"`
- `id eq "123"`
- `displayName co "Alice"`
- `active eq true`
- `active eq false`

Malformed or unsupported filters return a SCIM error with `scimType: invalidFilter`.

Sorting:

- `sortBy=id`
- `sortBy=userName`
- `sortBy=displayName`
- `sortOrder=ascending`
- `sortOrder=descending`

Unsupported sort fields return a SCIM error with `scimType: invalidPath`.

Attribute projection:

- `attributes=userName`
- `attributes=id,userName`
- `attributes=urn:ietf:params:scim:schemas:extension:enterprise:2.0:User`
- `excludedAttributes=meta`

Projection is applied to SCIM resources while preserving the required `schemas` and `id` identity fields.

### SCIM Group Query Parameters

`GET /scim/v2/Groups` returns a SCIM `ListResponse` with `schemas`, `totalResults`, `startIndex`, `itemsPerPage`, and `Resources`.

Pagination:

- `startIndex`: 1-based index of the first result. Default: `1`.
- `count`: maximum number of resources to return. Default: `100`.
- Out-of-range `startIndex` values return an empty `Resources` array with the requested `startIndex`.

Filters:

- `displayName eq "Admins"`
- `id eq "123"`
- `displayName co "Admin"`

Malformed or unsupported filters return a SCIM error with `scimType: invalidFilter`.

Sorting:

- `sortBy=id`
- `sortBy=displayName`
- `sortOrder=ascending`
- `sortOrder=descending`

Unsupported sort fields return a SCIM error with `scimType: invalidPath`.

Attribute projection:

- `attributes=displayName`
- `attributes=id,displayName`
- `excludedAttributes=members`

Projection is applied to SCIM Group resources while preserving the required `schemas` and `id` identity fields.

Future SCIM milestones:

- `Access Reviews`: review campaigns, decisions, and remediation.
- `AI Explanations`: explainable access and provisioning decisions using deterministic system context.

## Connector Framework

AccessIQ includes a synchronous connector framework for future outbound provisioning delivery. It intentionally does not call Salesforce, GitHub, Zendesk, Finance, Microsoft Entra ID, Okta, Ping Identity, SailPoint, ForgeRock, OneLogin, or any other external service.

```text
Domain Event or Service Request
  -> Provisioning Orchestrator
  -> Provisioning Job
  -> Connector Registry
  -> IdentityConnector implementation
  -> ConnectorResult
  -> Provisioning History
  -> Audit Logging
  -> Domain Events
```

The framework lives under `app/connectors`:

- `IdentityConnector`: abstract interface for user, group, and entitlement operations.
- `ConnectorRegistry`: registers, lists, and resolves enabled connectors by name.
- `ProvisioningOrchestrator`: executes connector operations, applies retry decisions, writes audit events when audit context is supplied, and publishes connector domain events.
- `RetryPolicy`: calculates retry decisions and backoff delays without sleeping.
- `ConnectorResult`: structured result model with connector, operation, status, message, timestamp, duration, retryability, correlation ID, and details.
- `ConnectorError` subclasses: reusable authentication, authorization, validation, rate limit, timeout, retryable, and configuration errors.
- Mock connectors: deterministic Salesforce, GitHub, Zendesk, and Finance implementations.

Supported connector operations:

- `create_user`
- `update_user`
- `disable_user`
- `delete_user`
- `create_group`
- `update_group`
- `delete_group`
- `add_group_member`
- `remove_group_member`
- `grant_entitlement`
- `revoke_entitlement`

Connector result statuses:

- `SUCCESS`
- `FAILED`
- `RETRYABLE`
- `SKIPPED`

Connector health states:

- `HEALTHY`
- `DEGRADED`
- `UNAVAILABLE`

The read-only connector metadata endpoints are protected by existing JWT and API RBAC:

```bash
curl http://localhost:8000/connectors \
  -H "Authorization: Bearer <jwt>"

curl http://localhost:8000/connectors/salesforce/health \
  -H "Authorization: Bearer <jwt>"
```

Connector executions use the seeded `Connector Framework` application and `Connector Execution` entitlement for audit events. The current framework is synchronous by design; future background workers can subscribe to domain events and invoke the same orchestrator without refactoring connector implementations.

## Provisioning Job Engine

AccessIQ persists connector execution tracking in normalized provisioning job and history tables. This establishes the foundation for future retry schedulers, dashboards, reporting, and AI explanations without adding asynchronous processing.

Every orchestrated connector execution with a database context follows this lifecycle:

```text
ProvisioningJob
  -> Connector invocation
  -> ConnectorResult
  -> ProvisioningHistory
  -> AuditEvent
  -> Domain events
```

`ProvisioningJob` stores the current state of one connector execution:

- `correlation_id`
- `connector`
- `operation`
- `target_type`
- `target_id`
- `status`
- `attempt_count`
- `retry_count`
- `max_attempts`
- `retryable`
- `last_error`
- timestamps and duration

`ProvisioningHistory` stores immutable event entries such as job created, job started, connector invocation, connector result, retry recorded, job completed, and job failed.

Correlation IDs are generated automatically when a caller does not provide one. The same correlation ID is propagated across provisioning jobs, connector results, provisioning history, audit events, and domain events.

Read-only provisioning activity endpoints:

```bash
curl "http://localhost:8000/provisioning/jobs?connector=salesforce" \
  -H "Authorization: Bearer <jwt>"

curl "http://localhost:8000/provisioning/history?correlation_id=<id>" \
  -H "Authorization: Bearer <jwt>"
```

Supported job filters include `connector`, `operation`, `status`, `correlation_id`, `target_type`, and `target_id`. Supported history filters include `job_id`, `connector`, `operation`, `event_type`, `status`, and `correlation_id`. Both endpoints support `start_index`, `count`, `sort_by`, and `sort_order`.

Milestone 7B records retry decisions as history entries and audit events. It does not implement scheduled retries, queues, background workers, or asynchronous execution.

## Access Reviews And Certification Campaigns

AccessIQ includes an identity governance layer for access certification campaigns. A campaign snapshots current access assignments into review items, records reviewer decisions, and preserves those decisions for future remediation. It does not revoke access, call connectors, or run background processing.

```text
REST API
  -> JWT Authentication
  -> API RBAC
  -> Governance Services
  -> Audit Logging
  -> Domain Events
  -> Database
```

Campaign lifecycle:

- `DRAFT`: campaign has been created but review items have not been generated.
- `ACTIVE`: current access assignments have been captured as review items.
- `COMPLETED`: all review items have a recorded decision.
- `CANCELLED`: campaign is closed without completing certification.

Review decisions:

- `APPROVE`: access is certified as still appropriate.
- `REVOKE`: access is marked for future remediation.
- `ABSTAIN`: reviewer records no certification decision.

Read/write examples:

```bash
curl -X POST http://localhost:8000/access-reviews/campaigns \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"name":"Q3 Access Review","reviewer_id":1}'

curl -X POST http://localhost:8000/access-reviews/campaigns/1/start \
  -H "Authorization: Bearer <jwt>"

curl -X POST http://localhost:8000/access-reviews/items/1/decision \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"decision":"REVOKE","comments":"No longer required"}'
```

Summary endpoints expose pending item count, completed item count, approval count, revocation count, abstain count, and completion percentage. Revoke decisions are governance records only; a future remediation worker can consume them and invoke the provisioning engine.

## Policy Enforcement And Audit Logging

AccessIQ uses deterministic Python policy checks for access grants and revokes. It does not call AI, LLMs, or external policy services.

API RBAC is not the business policy engine. A caller must first be authorized to call an endpoint, and then the policy engine evaluates whether the requested access change is allowed.

Grant policy rules:

- Inactive target users cannot receive access.
- The requester must be active.
- Auditors and employees cannot grant access.
- Finance Portal access is restricted to users in the Finance department.
- Administrator entitlements can only be granted by admin operators.
- Help Desk users can grant standard, non-administrator entitlements.
- Admin operators can grant standard and administrator entitlements.

Grant and revoke request bodies identify only the target and entitlement:

```json
{
  "target_user_id": 2,
  "entitlement_id": 3
}
```

The requester is always derived from the bearer token and cannot be supplied by the client.

Successful grant/revoke attempts and business-policy denials are written to the audit log. API RBAC denials happen before the business policy engine and are not access-governance audit events. Audit events can be listed newest first by authorized callers:

```bash
curl http://localhost:8000/audit-events \
  -H "Authorization: Bearer <jwt>"
curl "http://localhost:8000/audit-events?requester_id=1" \
  -H "Authorization: Bearer <jwt>"
curl "http://localhost:8000/audit-events?target_user_id=2" \
  -H "Authorization: Bearer <jwt>"
curl "http://localhost:8000/audit-events?action=grant" \
  -H "Authorization: Bearer <jwt>"
curl "http://localhost:8000/audit-events?result=denied" \
  -H "Authorization: Bearer <jwt>"
curl "http://localhost:8000/audit-events?correlation_id=<id>" \
  -H "Authorization: Bearer <jwt>"
```

This is a basic audit trail for development and validation, not a complete production compliance system.
