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

## SCIM 2.0 User Read Operations

SCIM, the System for Cross-domain Identity Management, is the protocol enterprise identity providers use to automate identity lifecycle operations. Products such as Microsoft Entra ID, Okta, Ping Identity, Google Workspace, SailPoint, and OneLogin use SCIM to exchange user and group data with downstream applications.

AccessIQ implements SCIM 2.0 metadata endpoints and read-only User resources. It does not provision users or groups yet: `POST /Users`, `PATCH /Users`, `PUT /Users`, `DELETE /Users`, and `/Groups` are intentionally not implemented until later milestones.

```text
AccessIQ REST API
  -> SCIM API
  -> Future connector framework
```

The REST API remains the native AccessIQ API. The SCIM API is isolated under `app/scim` so future provisioning and connector work can build on protocol-specific models without coupling to the existing REST route handlers.

SCIM endpoints use the SCIM media type `application/scim+json`, return SCIM-shaped error payloads, and are protected with the existing JWT authentication and API RBAC layers. Dedicated SCIM bearer tokens can be added later without changing the SCIM metadata model.

| Endpoint | Status | Required Role(s) |
| --- | --- | --- |
| `GET /scim/v2/ServiceProviderConfig` | Implemented metadata | `security_admin`, `iam_admin` |
| `GET /scim/v2/ResourceTypes` | Implemented metadata | `security_admin`, `iam_admin` |
| `GET /scim/v2/Schemas` | Implemented metadata | `security_admin`, `iam_admin` |
| `GET /scim/v2/Users` | Implemented read operation | `security_admin`, `iam_admin` |
| `GET /scim/v2/Users/{id}` | Implemented read operation | `security_admin`, `iam_admin` |
| `GET /scim/v2/Groups` | Future milestone | Not implemented |

### SCIM User Resource

AccessIQ maps existing `User` rows into SCIM User resources:

- `id`: AccessIQ user ID serialized as a SCIM string ID.
- `userName`: user email address.
- `displayName`: AccessIQ display name.
- `name.formatted`: AccessIQ display name.
- `active`: AccessIQ active flag.
- `emails`: primary work email derived from the user email address.
- `meta.resourceType`: `User`.
- `meta.location`: canonical SCIM resource URL.

`meta.lastModified` is omitted because AccessIQ does not yet store a user modification timestamp. Unsupported SCIM attributes are omitted rather than populated with placeholder values.

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
- `excludedAttributes=meta`

Projection is applied to SCIM resources while preserving the required `schemas` and `id` identity fields.

Future SCIM milestones:

- `6C User Provisioning`: create, update, patch, deactivate, and delete SCIM users.
- `Future Groups`: group metadata, group membership, and group provisioning.
- `Future Enterprise Extensions`: enterprise user extension mapping and lifecycle fields.

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
```

This is a basic audit trail for development and validation, not a complete production compliance system.
