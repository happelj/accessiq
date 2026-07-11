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

## SCIM 2.0 Foundation

SCIM, the System for Cross-domain Identity Management, is the protocol enterprise identity providers use to automate identity lifecycle operations. Products such as Microsoft Entra ID, Okta, Ping Identity, Google Workspace, SailPoint, and OneLogin use SCIM to exchange user and group data with downstream applications.

AccessIQ currently implements the SCIM 2.0 protocol foundation only. It exposes metadata endpoints that enterprise IdPs expect during setup, but it does not provision users or groups yet.

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
| `GET /scim/v2/Users` | Future Milestone 6B | Not implemented |
| `GET /scim/v2/Groups` | Future Milestone 6C | Not implemented |

Future SCIM milestones:

- `6B User Provisioning`: create, read, update, deactivate, and list SCIM users.
- `6C Groups`: group metadata, group membership, and group provisioning.
- `6D Enterprise Extensions`: enterprise user extension mapping and lifecycle fields.

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
