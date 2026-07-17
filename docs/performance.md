# Performance, Scale, and Resiliency Validation

Milestone 16B adds repeatable performance validation for AccessIQ without
changing API behavior. The framework focuses on measurable latency, throughput,
error rate, database behavior, frontend bundle characteristics, Kubernetes
scaling, and AWS sizing guidance.

## Methodology

Use the k6 scripts in `performance/k6` against a running AccessIQ API. The
scripts use deterministic seeded data and avoid destructive operations. The only
write-like requests are authentication and mock AI explanation/context requests,
which do not mutate identity, access, SCIM, review, or provisioning state.

Recommended baseline process:

1. Start AccessIQ with Docker Compose or Kubernetes.
2. Confirm `GET /health` and `GET /metrics` return `200`.
3. Run `performance/k6/health.js` as a smoke check.
4. Run focused scripts for the subsystem being changed.
5. Run `performance/k6/full-system.js` before merging.
6. Capture k6 summary output and Prometheus metric deltas.

Default thresholds are intentionally conservative for local validation:

- HTTP failure rate below 1 percent for focused scripts.
- Full-system HTTP failure rate below 2 percent.
- Focused P95 latency below 750-1500 ms depending on endpoint type.
- Full-system P95 latency below 1500 ms and P99 below 3000 ms.

## k6 Scenarios

| Script | Coverage | Destructive |
| --- | --- | --- |
| `auth.js` | Login and health after authentication | No |
| `users.js` | Users and user access reads | No |
| `applications.js` | Applications and entitlements | No |
| `scim.js` | SCIM metadata, users, and groups | No |
| `graph.js` | Authorization graph node, evidence, access, and path reads | No |
| `ai.js` | AI providers, deterministic context, and mock explanation | No |
| `reviews.js` | Access review campaigns and items | No |
| `provisioning.js` | Provisioning jobs, history, and remediation reads | No |
| `health.js` | Health, version, and metrics | No |
| `full-system.js` | Mixed system read path and mock AI explain | No |

Run a quick local smoke:

```bash
k6 run performance/k6/health.js
```

Run a broader baseline:

```bash
K6_VUS=5 K6_DURATION=5m k6 run performance/k6/full-system.js
```

Docker Desktop for Windows:

```powershell
docker run --rm -i `
  -e ACCESSIQ_BASE_URL=http://host.docker.internal:8000 `
  -e K6_VUS=5 `
  -e K6_DURATION=5m `
  -v "${PWD}:/workspace" `
  grafana/k6:0.54.0 run /workspace/performance/k6/full-system.js
```

## Baseline Metrics To Record

Record the following after every milestone that touches backend, frontend,
database, Helm, Terraform, or observability behavior:

| Metric | Source | Target For Local Smoke |
| --- | --- | --- |
| Average latency | k6 `http_req_duration avg` | Track trend |
| Median latency | k6 `http_req_duration med` | Track trend |
| P95 latency | k6 `http_req_duration p(95)` | Under scenario threshold |
| P99 latency | k6 `http_req_duration p(99)` | Under scenario threshold |
| Throughput | k6 `http_reqs` rate | Track trend |
| Error rate | k6 `http_req_failed` | Below threshold |
| API request rate | Prometheus `accessiq_http_requests_total` | Increases during test |
| API latency buckets | Prometheus `accessiq_http_request_duration_seconds` | Bucket counts increase |
| DB query count | Prometheus `accessiq_database_queries_total` | Increases for health checks |
| CPU/memory | `kubectl top pods` or Docker Desktop | No sustained saturation |

Example baseline entry format:

```text
Date:
Git SHA:
Environment:
Command:
VUs / duration:
avg / med / p95 / p99:
requests/sec:
error rate:
CPU / memory:
Notes:
```

## Initial Local Baseline

Captured on July 17, 2026 with Docker Compose API, PostgreSQL container, Docker
Desktop for Windows, and `grafana/k6:0.54.0`.

| Scenario | VUs | Duration | Requests | Throughput | Error Rate | Avg | Median | P95 | P99 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `health.js` | 1 | 10s | 30 | 2.91 req/s | 0.00% | 9.70 ms | 8.38 ms | 18.83 ms | under 20.27 ms max |
| `full-system.js` | 1 | 10s | 127 | 11.49 req/s | 0.00% | 15.81 ms | 9.44 ms | 42.58 ms | under 424.36 ms max |

The `full-system.js` run validated login, health, version, metrics, users,
applications, entitlements, SCIM metadata/users/groups, graph evidence, access
reviews, provisioning jobs, and mock AI explanation with all checks passing.

## Database Review

Current high-volume read paths already use practical indexes:

- `users.email` is unique and indexed for login and lookup.
- `groups.display_name` is unique and indexed for SCIM group lookup.
- SCIM enterprise user `user_id`, `employee_number`, and `manager_id` are indexed.
- Audit, provisioning, release, governance, remediation, and delegation filters use
  indexed columns for common list endpoints.
- `AccessAssignment` has a unique `(user_id, entitlement_id)` constraint that
  supports access grant duplicate checks and user access reads.

The performance review did not add new schema indexes because the current k6
coverage is read-heavy and no measured query bottleneck justified a migration.
Future work should capture `EXPLAIN ANALYZE` output from production-like
PostgreSQL data before adding additional composite indexes.

## Connection Pooling

SQLAlchemy engine tuning is now configurable for non-SQLite databases:

| Environment Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_POOL_PRE_PING` | `true` | Checks pooled connections before reuse |
| `DATABASE_POOL_SIZE` | `5` | Persistent connections per backend process |
| `DATABASE_MAX_OVERFLOW` | `10` | Temporary overflow connections per process |
| `DATABASE_POOL_TIMEOUT` | `30` | Seconds to wait for a pooled connection |
| `DATABASE_POOL_RECYCLE_SECONDS` | `1800` | Recycle age for long-lived connections |

SQLite keeps its existing local behavior and does not receive QueuePool sizing
arguments. For Kubernetes, calculate maximum database connections as:

```text
backend replicas * gunicorn/uvicorn worker processes * (pool_size + max_overflow)
```

Keep that number below the RDS `max_connections` budget after reserving headroom
for migrations, admin sessions, monitoring, and future workers.

## Frontend Bundle Review

The React router now lazy-loads page modules with `React.lazy` and `Suspense`.
This keeps the login shell, layout, and shared components available while moving
feature pages into route-level chunks. The expected result is a smaller initial
JavaScript payload and clearer build output for future bundle analysis.

Measure bundle output with:

```bash
npm --prefix frontend run build
```

Review generated chunk sizes under `frontend/dist/assets`.

Initial build output after route-level lazy loading:

- Main JavaScript chunk: `194.96 kB`, gzip `62.89 kB`.
- Feature page chunks: individual route chunks from roughly `0.40 kB` to
  `5.00 kB`.
- Shared component chunks include `PageHeader` at `9.98 kB`, gzip `3.64 kB`,
  and React JSX runtime at `7.62 kB`, gzip `2.93 kB`.

## Kubernetes Scaling Validation

Local scale-up:

```bash
kubectl -n accessiq-dev scale deployment/accessiq-backend --replicas=2
kubectl -n accessiq-dev rollout status deployment/accessiq-backend
kubectl -n accessiq-dev get pods -l app.kubernetes.io/component=backend
```

Run load while scaled:

```bash
K6_VUS=10 K6_DURATION=5m k6 run performance/k6/full-system.js
```

Validate HPA rendering:

```bash
helm template accessiq helm/accessiq -f helm/accessiq/values-prod.yaml | kubectl apply --dry-run=client -f -
```

When metrics-server is installed, validate HPA behavior:

```bash
kubectl -n accessiq-dev get hpa
kubectl -n accessiq-dev top pods
kubectl -n accessiq-dev describe hpa accessiq-backend
```

Probe stability checks:

```bash
kubectl -n accessiq-dev describe deployment/accessiq-backend
kubectl -n accessiq-dev get events --sort-by=.lastTimestamp
```

Milestone validation on July 17, 2026:

- Helm upgrade to `accessiq-dev` succeeded with chart revision 2.
- `helm test accessiq --namespace accessiq-dev` succeeded.
- Backend rollout succeeded before scaling.
- Manual backend scale from 1 replica to 2 replicas completed successfully.
- Both backend pods reached `1/1 Running`.
- Dev HPA check returned no resources, which matches `values-dev.yaml` where
  autoscaling is disabled.
- Production Helm rendering includes backend and frontend HPAs with the configured
  replica ranges.
- Backend was scaled back to the dev default of 1 replica after validation.

## Observability Interpretation

During a k6 run:

- `accessiq_http_requests_total` should increase by method, path, and status.
- `accessiq_http_request_duration_seconds_bucket` should show latency distribution.
- `accessiq_ai_provider_requests_total` should increase during `ai.js` and
  `full-system.js`.
- `accessiq_scim_requests_total` should increase during `scim.js`.
- `accessiq_database_queries_total` should increase during health checks.

Prometheus examples:

```promql
sum(rate(accessiq_http_requests_total[5m]))
sum(rate(accessiq_http_requests_total{status_code=~"5.."}[5m]))
histogram_quantile(0.95, sum(rate(accessiq_http_request_duration_seconds_bucket[5m])) by (le))
sum(rate(accessiq_ai_provider_requests_total[5m]))
```

## AWS Sizing Guidance

Start small for a demo or low-traffic environment:

- EKS node group: 2 nodes, `t3.medium` or equivalent.
- Backend: 2 replicas, request `250m` CPU and `512Mi` memory, limit `1` CPU and
  `1Gi` memory.
- Frontend: 2 replicas, request `100m` CPU and `128Mi` memory.
- RDS PostgreSQL: burstable small instance for demos; use production-grade
  Multi-AZ sizing only for real workloads.
- Database pool: start with `DATABASE_POOL_SIZE=5` and
  `DATABASE_MAX_OVERFLOW=10`, then tune from observed wait time and RDS
  connection pressure.
- HPA: backend min 2, max 6-10, target CPU 70 percent; frontend min 2, max 6-10.

For production capacity planning, run staged tests at 1x, 2x, and 4x expected
traffic, then size CPU, memory, and RDS connections from the highest sustainable
load with acceptable P95/P99 latency and error rate.

## Future Tuning

- Add a production-like seed dataset generator for high-cardinality access graphs.
- Capture PostgreSQL `EXPLAIN ANALYZE` plans for slow list endpoints.
- Add CI smoke mode for k6 when a runner image with k6 is available.
- Add bundle visualization when frontend dependency policy allows it.
- Add sustained soak tests for connector and remediation workflows once durable
  background processing exists.
