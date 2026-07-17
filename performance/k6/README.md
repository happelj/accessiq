# AccessIQ k6 Performance Suite

These scripts provide deterministic, non-destructive performance coverage for the
AccessIQ API. They use seeded users and read-only endpoints wherever possible.
The only POST requests are login and mock AI explanation/context calls.

## Requirements

- AccessIQ API running at `http://localhost:8000`, or set `ACCESSIQ_BASE_URL`.
- k6 installed locally, or Docker available for the `grafana/k6` image.
- Seed credential: `alice@example.com` / `Password123!`, unless overridden.

## Scripts

- `auth.js`: login throughput and basic post-login health check.
- `users.js`: user list, user detail, and user access reads.
- `applications.js`: application and entitlement catalog reads.
- `scim.js`: SCIM metadata, user reads, and group reads.
- `graph.js`: authorization graph node, evidence, access, and path reads.
- `ai.js`: provider health, deterministic context, and mock explanation.
- `reviews.js`: access review campaign and item reads.
- `provisioning.js`: provisioning, history, and remediation reads.
- `health.js`: health, version, and Prometheus metrics reads.
- `full-system.js`: mixed non-destructive system scenario.

## Run Locally

```bash
k6 run performance/k6/full-system.js
```

With Docker from the repository root:

```bash
docker run --rm -i \
  --network host \
  -e ACCESSIQ_BASE_URL=http://localhost:8000 \
  -v "$PWD:/workspace" \
  grafana/k6:0.54.0 run /workspace/performance/k6/full-system.js
```

On Docker Desktop for Windows, use `host.docker.internal`:

```powershell
docker run --rm -i `
  -e ACCESSIQ_BASE_URL=http://host.docker.internal:8000 `
  -v "${PWD}:/workspace" `
  grafana/k6:0.54.0 run /workspace/performance/k6/full-system.js
```

## Tunable Environment

- `ACCESSIQ_BASE_URL`: API base URL. Default: `http://localhost:8000`.
- `ACCESSIQ_TEST_EMAIL`: login email. Default: `alice@example.com`.
- `ACCESSIQ_TEST_PASSWORD`: login password. Default: `Password123!`.
- `K6_VUS`: constant virtual users. Default: `1`.
- `K6_DURATION`: test duration. Default: `30s`.

Example:

```bash
K6_VUS=10 K6_DURATION=5m k6 run performance/k6/full-system.js
```
