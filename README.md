# AccessIQ

Initial FastAPI service scaffold for AccessIQ.

## Development Note

AccessIQ was built as an AI-assisted software engineering project using ChatGPT and Codex.

ChatGPT was used to help shape the project roadmap, define milestones, and generate detailed implementation prompts. Codex was used to implement the codebase iteratively from those prompts. My role was to guide the project direction, review the generated plans and prompts, run the application, perform manual testing, troubleshoot issues, and validate that each milestone worked as intended.

This project demonstrates how AI-assisted development workflows can be used to build and iterate on a full-stack identity security platform, including backend APIs, frontend workflows, CI/CD, Docker, and Kubernetes packaging.

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

The Docker stack also includes a Vite frontend service at `http://localhost:5173`.
The frontend calls the API at `http://localhost:8000` by default.

Run the frontend outside Docker:

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Run frontend validation:

```bash
cd frontend
npm test
npm run build
```

## Documentation

- [Architecture](docs/architecture.md)
- [Frontend architecture](docs/frontend.md)
- [CI/CD quality gates](docs/ci-cd.md)
- [Kubernetes and Helm](docs/kubernetes.md)
- [AWS infrastructure](docs/aws.md)
- [AWS deployment](docs/deployment-aws.md)
- [Release engineering](docs/releases.md)
- [Observability](docs/observability.md)
- [Terraform workflow](docs/terraform.md)
- [SCIM implementation](docs/scim.md)
- [Connector framework](docs/connectors.md)
- [Provisioning jobs and history](docs/provisioning.md)
- [Access reviews and certification campaigns](docs/access_reviews.md)
- [Remediation engine](docs/remediation.md)
- [Delegated administration](docs/delegation.md)
- [Authorization graph](docs/graph.md)
- [AI context assembly](docs/ai.md)
- [Architecture decision records](docs/adr)

## Authentication And API Authorization

AccessIQ separates authentication, API authorization, business policy evaluation, and audit logging:

```text
JWT Authentication
  -> API RBAC
  -> Delegation Service
  -> Business Policy Engine
  -> Audit Logging
  -> Database
```

Authentication answers who the caller is. API RBAC decides whether that authenticated caller may invoke a REST endpoint or enter a delegated authorization path. The delegation service evaluates scoped authority for application, group, and entitlement administration. The business policy engine then evaluates the requested access change. These layers are intentionally separate so endpoint security does not leak into entitlement policy logic.

Passwords are hashed with Argon2 through `passlib`. Plaintext passwords are never stored or compared directly. Seed users receive development passwords during startup, and existing databases are upgraded safely by adding a `password_hash` column when it is missing.

JWT access tokens are signed locally and include standard `sub`, `iat`, and `exp` claims. The reusable `get_current_user()` dependency validates bearer tokens and loads the matching user.

### Configuration

Set these environment variables as needed:

- `DATABASE_URL`: SQLAlchemy database URL. Default: `sqlite:///./accessiq.db`.
- `JWT_SECRET`: signing secret for access tokens. Default is development-only.
- `JWT_ALGORITHM`: JWT signing algorithm. Default: `HS256`.
- `ACCESS_TOKEN_EXPIRE_MINUTES`: token lifetime in minutes. Default: `30`.
- `ACCESSIQ_LOGGER_NAME`: stdlib logger name used for structured JSON events. Default: `accessiq`.
- `ACCESSIQ_LOG_LEVEL`: stdlib logging level. Default: `INFO`.
- `ACCESSIQ_METRICS_ENABLED`: enables the Prometheus-format metrics endpoint. Default: `true`.
- `ACCESSIQ_TRACING_ENABLED`: enables OpenTelemetry tracing instrumentation. Default: `true`.
- `OTEL_SERVICE_NAME`: OpenTelemetry service name. Default: `accessiq-api`.
- `OTEL_EXPORTER_OTLP_ENDPOINT`: optional OpenTelemetry Collector OTLP endpoint.
- `AI_ENABLED`: enables AI explanation endpoints. Default: `true`.
- `LLM_PROVIDER`: configured explanation provider. Default: `mock`.
- `AI_TIMEOUT`: provider timeout in seconds. Default: `30`.
- `AI_MAX_TOKENS`: maximum provider output token budget. Default: `1200`.
- `OPENAI_API_KEY`: optional OpenAI API key. Missing keys make the OpenAI provider unavailable without failing startup.
- `ANTHROPIC_API_KEY`: optional Anthropic API key. Missing keys make the Anthropic provider unavailable without failing startup.
- `CORS_ALLOWED_ORIGINS`: comma-separated browser origins allowed to call the API. Default includes the Vite dev server.
- `CORS_ALLOW_CREDENTIALS`: whether CORS allows credentials. Default: `true`.
- `VITE_API_BASE_URL`: frontend build/runtime API base URL used by the Docker frontend service. Default: `http://localhost:8000`.
- `ENABLE_SALESFORCE_CONNECTOR`: enables the mock Salesforce connector. Default: `true`.
- `ENABLE_GITHUB_CONNECTOR`: enables the mock GitHub connector. Default: `true`.
- `ENABLE_ZENDESK_CONNECTOR`: enables the mock Zendesk connector. Default: `true`.
- `ENABLE_FINANCE_CONNECTOR`: enables the mock Finance connector. Default: `true`.
- `SALESFORCE_API_BASE_URL`, `GITHUB_API_BASE_URL`, `ZENDESK_API_BASE_URL`, `FINANCE_API_BASE_URL`: reserved for future real connector credentials and endpoints. Milestone 7A does not call external APIs.

Configuration access is centralized in `app/config.py`; routes and services should use the settings providers rather than reading environment variables directly.

## Frontend Admin Portal

The React admin portal lives in `frontend/`. It uses Vite, TypeScript, React Router, TanStack Query, a centralized API client, and an authentication context backed by the existing `POST /login` JWT flow.

Initial pages include dashboard, users, applications, groups, access assignments, SCIM metadata, connectors, provisioning jobs, access reviews, remediation, authorization graph, AI assistant, and settings. Pages call existing backend APIs where practical and display placeholders where a full UI workflow is still future work.

## CI/CD

AccessIQ uses GitHub Actions for pull request and `main` branch validation. The workflow runs backend linting, Python formatting checks, MyPy, the full backend test suite, frontend ESLint, Prettier checks, TypeScript validation, Vitest, frontend production build, Docker build validation, Kubernetes and Helm validation, and dependency security scans.

Run the same core checks locally:

```bash
python -m pip install -r requirements-dev.txt
ruff check app tests
black --check app tests
mypy
pytest -vv
pip-audit --requirement requirements.txt --strict --progress-spinner off

cd frontend
npm ci
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
npm audit --audit-level=moderate
```

Docker build validation:

```bash
docker build -t accessiq-api:ci .
docker build -t accessiq-frontend:ci frontend
```

The CI workflow does not require GitHub secrets and does not deploy or publish images. See [CI/CD quality gates](docs/ci-cd.md) for branch protection recommendations and troubleshooting.

## Kubernetes And Helm

AccessIQ includes a Helm chart at `helm/accessiq` for portable Kubernetes deployment. The chart renders the backend, frontend, optional development PostgreSQL, Services, ConfigMaps, Secrets, PVC, ServiceAccount, health probes, resource limits, security contexts, rolling update controls, optional HPAs, optional PDBs, optional NetworkPolicies, and Ingress resources.

Validate the chart locally:

```bash
helm lint helm/accessiq
helm template accessiq helm/accessiq -f helm/accessiq/values-dev.yaml
helm template accessiq helm/accessiq -f helm/accessiq/values-prod.yaml
helm template accessiq helm/accessiq -f helm/accessiq/values-dev.yaml | kubectl apply --dry-run=client -f -
```

Install on a local Kubernetes cluster:

```bash
helm upgrade --install accessiq helm/accessiq \
  --namespace accessiq-dev \
  --create-namespace \
  -f helm/accessiq/values-dev.yaml
```

The bundled PostgreSQL deployment is for development only. Production deployments should use a managed database or production-grade PostgreSQL deployment. Production values enable autoscaling, disruption budgets, NetworkPolicies, non-root containers, read-only root filesystems, and TLS ingress placeholders. CPU-based HPA behavior requires metrics-server. See [Kubernetes and Helm](docs/kubernetes.md) for values, secrets, ingress, upgrade, rollback, hardening, and troubleshooting guidance.

## AWS Infrastructure

AccessIQ includes Terraform infrastructure under `infrastructure/terraform` for a future AWS deployment path. The Terraform creates reusable AWS foundations for VPC networking, EKS, managed node groups, private PostgreSQL RDS, ECR repositories, IAM roles, and Secrets Manager placeholders.

Validate an environment from its directory:

```bash
cd infrastructure/terraform/environments/dev
terraform init
terraform validate
```

After the S3 remote backend has been bootstrapped, copy `backend.tf.example` to `backend.tf`, create `backend.hcl` from `backend.example.hcl`, and run:

```bash
terraform init -backend-config=backend.hcl
terraform plan
```

AWS deployment is available as an explicit, manual GitHub Actions workflow that builds immutable backend and frontend images, pushes them to ECR, deploys the Helm chart to EKS, verifies rollout, and runs smoke tests. See [AWS deployment](docs/deployment-aws.md) for OIDC, ECR, EKS, Helm, secrets, rollback, and troubleshooting guidance.

The infrastructure milestone does not automatically deploy AccessIQ to AWS, push Docker images, or configure GitHub Actions deployment on every commit. See [AWS infrastructure](docs/aws.md) for architecture, module details, costs, and cleanup guidance, and [Terraform workflow](docs/terraform.md) for remote state, backend bootstrap, planning, applying, destroying, and future CI guidance.

## Operations And Observability

Every request receives an `X-Correlation-ID`. If the caller supplies the header, AccessIQ preserves it; otherwise the middleware generates one and returns it in the response. The request context also stores request start time, client IP, user agent, and authenticated user metadata after JWT validation.

`GET /health` returns a structured report with top-level status, correlation ID, subsystem status, and lightweight in-memory counters. The current subsystems are database, connectors, audit, provisioning, domain events, and configuration.

`GET /version` returns release metadata including Git SHA, Git tag, build timestamp, Docker image, image digest, Helm chart version, Terraform version, and environment. Authenticated `GET /releases` and `GET /releases/current` expose application-level deployment history for security administrators, IAM administrators, and auditors. See [Release engineering](docs/releases.md) for metadata, versioning, rollback, and smoke-test guidance.

Operational events use stdlib logging with JSON payloads through `app/observability.py`. The same module exposes provider-backed Prometheus metrics at `GET /metrics`, including HTTP request counts and latency, authentication, RBAC denials, policy denials, connector execution, provisioning, review campaigns, remediation, AI provider calls, SCIM requests, database health checks, and release metadata.

OpenTelemetry tracing instruments FastAPI, SQLAlchemy, httpx, connector calls, and AI provider generation when tracing is enabled. Set `OTEL_EXPORTER_OTLP_ENDPOINT` to send spans to an OpenTelemetry Collector. Kubernetes deployments can enable Prometheus scrape annotations through Helm values. See [Observability](docs/observability.md) for metrics, logs, tracing, dashboard, alert, Kubernetes, and AWS guidance.

## Authorization Graph

AccessIQ includes a deterministic in-memory authorization graph under `app/graph`. The graph is a read model built from the relational database plus the connector registry. It does not make authorization decisions, mutate database rows, provision resources, or call external APIs.

The graph models users, groups, applications, entitlements, delegation assignments, certification campaigns, review items, provisioning jobs/history, remediation jobs, audit events, connectors, and enterprise profiles. It exposes evidence-backed read endpoints for access paths, manager chains, review history, remediation history, provisioning history, delegations, and shortest path traversal.

Graph endpoints require `security_admin`, `iam_admin`, or `auditor`:

- `GET /graph/users/{id}`
- `GET /graph/users/{id}/access`
- `GET /graph/users/{id}/evidence`
- `GET /graph/groups/{id}`
- `GET /graph/applications/{id}`
- `GET /graph/path`
- `GET /graph/export?format=json|mermaid|dot`
- `GET /graph/cache/status`
- `POST /graph/cache/refresh`
- `POST /graph/cache/invalidate`

Future AI explanation features can consume the graph and evidence collections, but Milestone 11A remains fully deterministic.

## AI Context Assembly

AccessIQ includes an AI explanation layer under `app/ai`. It classifies user questions, queries the authorization graph, collects and deduplicates evidence, applies heuristic ranking, enforces an approximate token budget, builds a structured prompt object, and asks a configured provider to explain only that evidence.

This layer does not use embeddings, pgvector, or semantic search. AI must not make authorization, provisioning, remediation, governance, or policy decisions. The provider may only explain deterministic evidence produced by AccessIQ.

```text
User Question
  -> Intent Classifier
  -> Authorization Graph Query Engine
  -> Evidence Collection
  -> Evidence Ranking
  -> Token Budget
  -> Context Assembly
  -> Prompt Builder
  -> LLM Provider
  -> Grounded Response
```

AI context endpoints require `security_admin`, `iam_admin`, or `auditor`:

- `POST /ai/context`
- `POST /ai/evidence`
- `POST /ai/prompt`
- `POST /ai/explain`
- `POST /ai/chat`
- `GET /ai/providers`

The default provider is `mock`, a deterministic provider that generates explanations directly from evidence without network access. Optional OpenAI and Anthropic provider adapters are available when configured with API keys; missing keys are reported through provider health and do not fail application startup.

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
| `POST /access/grant` | `security_admin`, `iam_admin`, or active scoped delegation |
| `POST /access/revoke` | `security_admin`, `iam_admin`, or active scoped delegation |
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
| `POST /access-reviews/campaigns/{campaign_id}/remediate` | `security_admin`, `iam_admin` |
| `GET /remediation/jobs` | `security_admin`, `iam_admin` |
| `GET /remediation/jobs/{job_id}` | `security_admin`, `iam_admin` |
| `POST /delegation/assignments` | `security_admin`, `iam_admin` |
| `GET /delegation/assignments` | `security_admin`, `iam_admin` |
| `GET /delegation/assignments/{assignment_id}` | `security_admin`, `iam_admin` |
| `DELETE /delegation/assignments/{assignment_id}` | `security_admin`, `iam_admin` |
| `GET /graph/users/{id}` | `security_admin`, `iam_admin`, `auditor` |
| `GET /graph/users/{id}/access` | `security_admin`, `iam_admin`, `auditor` |
| `GET /graph/users/{id}/evidence` | `security_admin`, `iam_admin`, `auditor` |
| `GET /graph/groups/{id}` | `security_admin`, `iam_admin`, `auditor` |
| `GET /graph/applications/{id}` | `security_admin`, `iam_admin`, `auditor` |
| `GET /graph/path` | `security_admin`, `iam_admin`, `auditor` |
| `GET /graph/export` | `security_admin`, `iam_admin`, `auditor` |
| `GET /graph/cache/status` | `security_admin`, `iam_admin`, `auditor` |
| `POST /graph/cache/refresh` | `security_admin`, `iam_admin`, `auditor` |
| `POST /graph/cache/invalidate` | `security_admin`, `iam_admin`, `auditor` |
| `POST /ai/context` | `security_admin`, `iam_admin`, `auditor` |
| `POST /ai/evidence` | `security_admin`, `iam_admin`, `auditor` |
| `POST /ai/prompt` | `security_admin`, `iam_admin`, `auditor` |
| `POST /ai/explain` | `security_admin`, `iam_admin`, `auditor` |
| `POST /ai/chat` | `security_admin`, `iam_admin`, `auditor` |
| `GET /ai/providers` | `security_admin`, `iam_admin`, `auditor` |

### Delegated Administration

Delegated administration lets AccessIQ grant scoped authority without making every operator a global administrator.

```text
JWT Authentication
  -> API RBAC
  -> DelegationService
  -> Business Policy Engine
  -> Access Mutation
  -> Audit Event
  -> Domain Events
```

Delegation assignments are normalized records with:

- delegate user
- scope type: `APPLICATION`, `GROUP`, or `ENTITLEMENT`
- scope ID
- delegation role
- creator
- optional expiration
- active flag

Supported delegation roles:

- `APPLICATION_OWNER`
- `APPLICATION_ADMINISTRATOR`
- `GROUP_OWNER`
- `GROUP_ADMINISTRATOR`
- `ACCESS_REVIEWER`
- `HELPDESK_DELEGATE`

The current access grant/revoke integration supports application and entitlement scoped delegations for `APPLICATION_OWNER`, `APPLICATION_ADMINISTRATOR`, and `HELPDESK_DELEGATE`. Delegation never skips business policy. For example, Finance Portal grants still require a Finance target user, and administrator entitlements require a stronger delegated role.

Example:

```bash
curl -X POST http://localhost:8000/delegation/assignments \
  -H "Authorization: Bearer <admin-jwt>" \
  -H "Content-Type: application/json" \
  -d '{
        "delegate_user_id": 2,
        "scope_type": "APPLICATION",
        "scope_id": 1,
        "delegation_role": "HELPDESK_DELEGATE"
      }'
```

Future organizational delegation can add `DEPARTMENT` and `ORGANIZATIONAL_UNIT` scopes without changing the current assignment lifecycle.

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

## Remediation Engine

AccessIQ can remediate completed certification campaigns by turning `REVOKE` decisions into provisioning-backed remediation jobs.

```text
Access Review
  -> CertificationDecision(REVOKE)
  -> RemediationJob
  -> ProvisioningOrchestrator
  -> ProvisioningJob
  -> ProvisioningHistory
  -> AuditEvent
  -> Domain events
```

The current remediation engine is synchronous and API-triggered. It does not add background workers, durable queues, notifications, approvals, or schedulers. Those can be layered on later because every remediation execution is stored as a normalized `RemediationJob` and linked to the provisioning job created by the existing orchestrator.

Supported remediation types:

- `REVOKE_ENTITLEMENT`
- `REMOVE_GROUP_MEMBER`
- `DISABLE_USER`

Current access review items are entitlement-backed, so completed `REVOKE` decisions execute `revoke_entitlement` connector operations. Non-revocation decisions are skipped.

Example:

```bash
curl -X POST http://localhost:8000/access-reviews/campaigns/1/remediate \
  -H "Authorization: Bearer <jwt>"

curl "http://localhost:8000/remediation/jobs?campaign_id=1" \
  -H "Authorization: Bearer <jwt>"
```

Remediation endpoints require `security_admin` or `iam_admin`.

## Policy Enforcement And Audit Logging

AccessIQ uses deterministic Python policy checks for access grants and revokes. It does not call AI, LLMs, or external policy services.

API RBAC is not the business policy engine. A caller must first be authorized to call an endpoint or satisfy an active delegation assignment, and then the policy engine evaluates whether the requested access change is allowed.

Grant policy rules:

- Inactive target users cannot receive access.
- The requester must be active.
- Auditors and employees cannot grant access unless they have an active matching delegation assignment.
- Finance Portal access is restricted to users in the Finance department.
- Administrator entitlements can only be granted by admin operators.
- Help Desk users can grant standard, non-administrator entitlements.
- Delegated helpdesk operators can grant or revoke standard scoped entitlements.
- Delegated application owners and application administrators can grant or revoke scoped administrator entitlements.
- Admin operators can grant standard and administrator entitlements.

Grant and revoke request bodies identify only the target and entitlement:

```json
{
  "target_user_id": 2,
  "entitlement_id": 3
}
```

The requester is always derived from the bearer token and cannot be supplied by the client.

Successful grant/revoke attempts and business-policy denials are written to the audit log. Delegation assignment changes and delegated action allow/deny decisions are also audited. API RBAC denials happen before the business policy engine and are not access-governance audit events. Audit events can be listed newest first by authorized callers:

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
