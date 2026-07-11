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

## Authentication

AccessIQ uses JWT bearer authentication for protected write and audit endpoints. Authentication answers who the caller is; authorization decisions remain in the deterministic policy engine.

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

Protected endpoints:

- `POST /access/grant`
- `POST /access/revoke`
- `GET /audit-events`

Public endpoints:

- `GET /health`
- `POST /login`

Milestone 5C will add API-level RBAC. The current milestone only ensures the acting requester is derived from the validated JWT instead of client-supplied request data.

## Policy Enforcement And Audit Logging

AccessIQ uses deterministic Python policy checks for access grants and revokes. It does not call AI, LLMs, or external policy services.

Supported operator roles:

- `administrator`
- `help_desk`
- `auditor`
- `employee`

Grant policy rules:

- Inactive target users cannot receive access.
- The requester must be active.
- Auditors and employees cannot grant access.
- Finance Portal access is restricted to users in the Finance department.
- Administrator entitlements can only be granted by administrators.
- Help Desk users can grant standard, non-administrator entitlements.
- Administrators can grant standard and administrator entitlements.

Grant and revoke request bodies identify only the target and entitlement:

```json
{
  "target_user_id": 2,
  "entitlement_id": 3
}
```

The requester is always derived from the bearer token and cannot be supplied by the client.

Successful and denied grant/revoke attempts are written to the audit log. Audit events can be listed newest first by authenticated callers:

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
