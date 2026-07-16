# Observability

Milestone 16A adds a portable observability platform for AccessIQ across local Kubernetes and Amazon EKS. The implementation covers metrics, structured logs, and tracing without requiring a specific managed monitoring vendor.

## Runtime Endpoints

- `GET /health`: structured subsystem health and lightweight in-memory counters.
- `GET /metrics`: Prometheus text-format metrics.
- `GET /version`: release metadata used by logs, metrics, dashboards, and deployment checks.

The `/metrics` endpoint is public so Prometheus can scrape it without a bearer token. Restrict external access through ingress, network policy, security groups, or Prometheus service discovery rules when exposing production clusters.

## Metrics

Metrics are exposed through a provider abstraction in `app/observability.py`. The default provider is `PrometheusProvider`, which renders Prometheus text format without coupling application logic to a Prometheus client package.

Standard metric families include:

- `accessiq_http_requests_total`
- `accessiq_http_request_duration_seconds`
- `accessiq_authentication_events_total`
- `accessiq_rbac_denials_total`
- `accessiq_policy_denials_total`
- `accessiq_connector_executions_total`
- `accessiq_connector_failures_total`
- `accessiq_connector_duration_seconds`
- `accessiq_provisioning_jobs_total`
- `accessiq_provisioning_job_duration_seconds`
- `accessiq_review_campaigns_total`
- `accessiq_review_decisions_total`
- `accessiq_remediation_jobs_total`
- `accessiq_ai_requests_total`
- `accessiq_ai_provider_requests_total`
- `accessiq_ai_provider_duration_seconds`
- `accessiq_scim_requests_total`
- `accessiq_database_queries_total`
- `accessiq_release_info`

Legacy lightweight counters remain available in `/health` for local debugging.

## Logs

Operational events use structured JSON payloads through `log_event`. Every event includes:

- timestamp
- service
- release
- version
- environment
- Git SHA
- event name
- status
- correlation ID when a request context exists
- request metadata
- authenticated user metadata when available

Set `ACCESSIQ_LOG_LEVEL` and `ACCESSIQ_LOGGER_NAME` to tune backend logging.

## Tracing

Tracing uses OpenTelemetry with a no-op fallback. When `ACCESSIQ_TRACING_ENABLED=true`, AccessIQ configures OpenTelemetry resource metadata and instruments:

- FastAPI requests
- SQLAlchemy database operations
- httpx client calls
- connector execution spans
- AI context assembly and provider generation spans

Set `OTEL_EXPORTER_OTLP_ENDPOINT` to export spans to an OpenTelemetry Collector. If the endpoint is empty, spans are created but not exported.

## Configuration

Environment variables:

```text
ACCESSIQ_METRICS_ENABLED=true
ACCESSIQ_TRACING_ENABLED=true
OTEL_SERVICE_NAME=accessiq-api
OTEL_EXPORTER_OTLP_ENDPOINT=
```

Helm values:

```yaml
backend:
  config:
    accessiqMetricsEnabled: "true"
    accessiqTracingEnabled: "true"
    otelServiceName: accessiq-api
    otelExporterOtlpEndpoint: ""

observability:
  prometheus:
    scrape: true
    path: /metrics
    port: "8000"
```

## Prometheus

The backend pod template renders these scrape annotations when `observability.prometheus.scrape=true`:

```yaml
prometheus.io/scrape: "true"
prometheus.io/path: "/metrics"
prometheus.io/port: "8000"
```

Example alert rules are in `docs/observability/prometheus-alerts.yaml`.

## Grafana

Import `docs/observability/accessiq-grafana-dashboard.json` into Grafana. The dashboard includes panels for request rate, 5xx rate, latency, authentication, RBAC/policy denials, connector failures, provisioning jobs, review decisions, remediation jobs, AI provider calls, and release metadata.

## AWS

For EKS, use one of these patterns:

- CloudWatch Logs: send container stdout/stderr to CloudWatch with Fluent Bit or the Amazon CloudWatch Observability add-on.
- OpenTelemetry Collector: deploy the collector as a DaemonSet or Deployment and set `OTEL_EXPORTER_OTLP_ENDPOINT` to the collector service.
- Amazon Managed Service for Prometheus: configure a scraper or collector pipeline for `/metrics`.
- Amazon Managed Grafana: connect Grafana to Managed Prometheus and import the AccessIQ dashboard JSON.

See `docs/deployment-aws.md` for the AWS deployment workflow and `docs/kubernetes.md` for Helm values.

## Manual Validation

After starting the API:

```bash
curl http://localhost:8000/metrics
curl http://localhost:8000/health
curl http://localhost:8000/version
```

In Kubernetes:

```bash
kubectl -n accessiq-dev get pod -l app.kubernetes.io/component=backend -o yaml
kubectl -n accessiq-dev port-forward svc/accessiq-backend 8000:8000
curl http://localhost:8000/metrics
```

Confirm that the backend pod has the Prometheus scrape annotations and that `/metrics` contains `accessiq_http_requests_total`, `accessiq_http_request_duration_seconds`, and `accessiq_release_info`.
