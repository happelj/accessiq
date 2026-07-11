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

Grant and revoke requests include the acting requester:

```json
{
  "requester_id": 1,
  "user_id": 2,
  "entitlement_id": 3
}
```

Successful and denied grant/revoke attempts are written to the audit log. Audit events can be listed newest first:

```bash
curl http://localhost:8000/audit-events
curl "http://localhost:8000/audit-events?requester_id=1"
curl "http://localhost:8000/audit-events?target_user_id=2"
curl "http://localhost:8000/audit-events?action=grant"
curl "http://localhost:8000/audit-events?result=denied"
```

This is a basic audit trail for development and validation, not a complete production compliance system.
