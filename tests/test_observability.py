import json
import logging

from fastapi.testclient import TestClient

from app.main import app
from app.observability import (
    NoopTracingProvider,
    PrometheusProvider,
    log_event,
    metrics_registry,
)


def test_prometheus_provider_renders_counters_histograms_and_gauges() -> None:
    provider = PrometheusProvider()

    provider.increment_counter(
        "accessiq_test_events_total",
        labels={"result": "succeeded"},
        description="Test events.",
    )
    provider.observe_histogram(
        "accessiq_test_duration_seconds",
        0.12,
        labels={"operation": "unit"},
        buckets=(0.1, 0.5),
        description="Test duration.",
    )
    provider.set_gauge(
        "accessiq_test_info",
        1,
        labels={"version": "test"},
        description="Test info.",
    )

    rendered = provider.render()

    assert "# TYPE accessiq_test_events_total counter" in rendered
    assert 'accessiq_test_events_total{result="succeeded"} 1' in rendered
    assert "# TYPE accessiq_test_duration_seconds histogram" in rendered
    assert (
        'accessiq_test_duration_seconds_bucket{operation="unit",le="0.5"} 1' in rendered
    )
    assert 'accessiq_test_info{version="test"} 1' in rendered


def test_metrics_endpoint_exposes_prometheus_text_format() -> None:
    with TestClient(app) as client:
        client.get("/health")
        response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "accessiq_http_requests_total" in body
    assert "accessiq_http_request_duration_seconds_bucket" in body
    assert "accessiq_database_queries_total" in body
    assert "accessiq_release_info" in body


def test_authentication_metrics_are_recorded() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/login",
            json={
                "email": "alice@example.com",
                "password": "Password123!",
            },
        )

    assert response.status_code == 200
    rendered = metrics_registry.render_prometheus()
    assert 'accessiq_authentication_events_total{result="succeeded"}' in rendered


def test_noop_tracing_provider_records_attributes() -> None:
    provider = NoopTracingProvider()

    with provider.span(
        "unit-test",
        attributes={"component": "observability"},
    ) as span:
        span.set_attribute("status", "succeeded")

    assert span.name == "unit-test"
    assert span.attributes["component"] == "observability"
    assert span.attributes["status"] == "succeeded"


def test_structured_log_event_includes_release_metadata(caplog) -> None:
    logger_name = "accessiq"
    caplog.set_level(logging.INFO, logger=logger_name)

    log_event("observability_test", status="succeeded", detail="unit")

    payloads = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == logger_name and "observability_test" in record.message
    ]

    assert payloads
    payload = payloads[-1]
    assert payload["event"] == "observability_test"
    assert payload["service"] == "accessiq"
    assert payload["release"]
    assert payload["version"] == payload["release"]
    assert payload["environment"]
