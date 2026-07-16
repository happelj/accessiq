from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
import importlib
import json
import logging
import re
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from .config import (
    get_logging_settings,
    get_observability_settings,
    get_release_settings,
)
from .request_context import get_request_context

MetricLabels = Mapping[str, str | int | float | bool | None]
LabelSet = tuple[tuple[str, str], ...]

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
DEFAULT_HISTOGRAM_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


@dataclass
class HistogramState:
    buckets: tuple[float, ...]
    bucket_counts: dict[float, int] = field(default_factory=dict)
    inf_count: int = 0
    count: int = 0
    total: float = 0.0

    def observe(self, value: float) -> None:
        self.count += 1
        self.total += value
        for bucket in self.buckets:
            if value <= bucket:
                self.bucket_counts[bucket] = self.bucket_counts.get(bucket, 0) + 1
                return

        self.inf_count += 1


class MetricsProvider:
    def increment_counter(
        self,
        name: str,
        *,
        amount: float = 1.0,
        labels: MetricLabels | None = None,
        description: str | None = None,
    ) -> None:
        raise NotImplementedError

    def set_gauge(
        self,
        name: str,
        value: float,
        *,
        labels: MetricLabels | None = None,
        description: str | None = None,
    ) -> None:
        raise NotImplementedError

    def observe_histogram(
        self,
        name: str,
        value: float,
        *,
        labels: MetricLabels | None = None,
        buckets: tuple[float, ...] = DEFAULT_HISTOGRAM_BUCKETS,
        description: str | None = None,
    ) -> None:
        raise NotImplementedError

    def render(self) -> str:
        raise NotImplementedError


class PrometheusProvider(MetricsProvider):
    def __init__(self) -> None:
        self._counters: dict[tuple[str, LabelSet], float] = {}
        self._gauges: dict[tuple[str, LabelSet], float] = {}
        self._histograms: dict[tuple[str, LabelSet], HistogramState] = {}
        self._descriptions: dict[str, str] = {}
        self._lock = Lock()

    def increment_counter(
        self,
        name: str,
        *,
        amount: float = 1.0,
        labels: MetricLabels | None = None,
        description: str | None = None,
    ) -> None:
        metric_name = _sanitize_metric_name(name)
        key = (metric_name, _normalize_labels(labels))
        with self._lock:
            self._remember_description(metric_name, description)
            self._counters[key] = self._counters.get(key, 0.0) + amount

    def set_gauge(
        self,
        name: str,
        value: float,
        *,
        labels: MetricLabels | None = None,
        description: str | None = None,
    ) -> None:
        metric_name = _sanitize_metric_name(name)
        key = (metric_name, _normalize_labels(labels))
        with self._lock:
            self._remember_description(metric_name, description)
            self._gauges[key] = value

    def observe_histogram(
        self,
        name: str,
        value: float,
        *,
        labels: MetricLabels | None = None,
        buckets: tuple[float, ...] = DEFAULT_HISTOGRAM_BUCKETS,
        description: str | None = None,
    ) -> None:
        metric_name = _sanitize_metric_name(name)
        key = (metric_name, _normalize_labels(labels))
        with self._lock:
            self._remember_description(metric_name, description)
            histogram = self._histograms.get(key)
            if histogram is None:
                histogram = HistogramState(
                    buckets=tuple(sorted(set(buckets))),
                    bucket_counts={bucket: 0 for bucket in buckets},
                )
                self._histograms[key] = histogram
            histogram.observe(value)

    def render(self) -> str:
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            histograms = {
                key: HistogramState(
                    buckets=value.buckets,
                    bucket_counts=dict(value.bucket_counts),
                    inf_count=value.inf_count,
                    count=value.count,
                    total=value.total,
                )
                for key, value in self._histograms.items()
            }
            descriptions = dict(self._descriptions)

        lines: list[str] = []
        for name in sorted({metric_name for metric_name, _ in counters}):
            lines.extend(_render_metric_header(name, "counter", descriptions))
            for (metric_name, labels), value in sorted(counters.items()):
                if metric_name == name:
                    lines.append(
                        f"{name}{_format_labels(labels)} {_format_value(value)}"
                    )

        for name in sorted({metric_name for metric_name, _ in gauges}):
            lines.extend(_render_metric_header(name, "gauge", descriptions))
            for (metric_name, labels), value in sorted(gauges.items()):
                if metric_name == name:
                    lines.append(
                        f"{name}{_format_labels(labels)} {_format_value(value)}"
                    )

        for name in sorted({metric_name for metric_name, _ in histograms}):
            lines.extend(_render_metric_header(name, "histogram", descriptions))
            for (metric_name, labels), histogram in sorted(histograms.items()):
                if metric_name != name:
                    continue
                cumulative = 0
                for bucket in histogram.buckets:
                    cumulative += histogram.bucket_counts.get(bucket, 0)
                    bucket_labels = (*labels, ("le", _format_bucket(bucket)))
                    lines.append(
                        f"{name}_bucket{_format_labels(bucket_labels)} {cumulative}"
                    )
                cumulative += histogram.inf_count
                inf_labels = (*labels, ("le", "+Inf"))
                lines.append(f"{name}_bucket{_format_labels(inf_labels)} {cumulative}")
                lines.append(f"{name}_count{_format_labels(labels)} {histogram.count}")
                lines.append(
                    f"{name}_sum{_format_labels(labels)} "
                    f"{_format_value(histogram.total)}"
                )

        lines.append("")
        return "\n".join(lines)

    def _remember_description(self, name: str, description: str | None) -> None:
        if description:
            self._descriptions.setdefault(name, description)


class MetricsRegistry:
    def __init__(self, provider: MetricsProvider | None = None) -> None:
        self._counters: dict[str, int] = {}
        self.provider = provider or PrometheusProvider()
        self._lock = Lock()

    def increment(
        self,
        name: str,
        amount: int = 1,
        *,
        labels: MetricLabels | None = None,
        description: str | None = None,
    ) -> None:
        with self._lock:
            if labels is None:
                self._counters[name] = self._counters.get(name, 0) + amount
        self.provider.increment_counter(
            name,
            amount=float(amount),
            labels=labels,
            description=description,
        )

    def set_gauge(
        self,
        name: str,
        value: float,
        *,
        labels: MetricLabels | None = None,
        description: str | None = None,
    ) -> None:
        self.provider.set_gauge(
            name,
            value,
            labels=labels,
            description=description,
        )

    def observe(
        self,
        name: str,
        value: float,
        *,
        labels: MetricLabels | None = None,
        buckets: tuple[float, ...] = DEFAULT_HISTOGRAM_BUCKETS,
        description: str | None = None,
    ) -> None:
        self.provider.observe_histogram(
            name,
            value,
            labels=labels,
            buckets=buckets,
            description=description,
        )

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(sorted(self._counters.items()))

    def render_prometheus(self) -> str:
        _set_release_metrics()
        return self.provider.render()


metrics_registry = MetricsRegistry()


@dataclass
class NoopSpan:
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def record_exception(self, exc: BaseException) -> None:
        self.attributes["exception.type"] = exc.__class__.__name__
        self.attributes["exception.message"] = str(exc)


class TracingProvider:
    enabled = False

    @contextmanager
    def span(
        self,
        name: str,
        *,
        attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[Any]:
        raise NotImplementedError

    def instrument_fastapi(self, app: Any) -> None:
        del app

    def instrument_sqlalchemy(self, engine: Any) -> None:
        del engine

    def instrument_httpx(self) -> None:
        return None


class NoopTracingProvider(TracingProvider):
    @contextmanager
    def span(
        self,
        name: str,
        *,
        attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[NoopSpan]:
        span = NoopSpan(name=name, attributes=dict(attributes or {}))
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            raise


class OpenTelemetryTracingProvider(TracingProvider):
    def __init__(self) -> None:
        self.enabled = False
        self._tracer: Any | None = None
        self._trace_module: Any | None = None

    def configure(self) -> None:
        settings = get_observability_settings()
        if not settings.tracing_enabled:
            return

        try:
            trace_module = importlib.import_module("opentelemetry.trace")
            resource_module = importlib.import_module("opentelemetry.sdk.resources")
            sdk_trace_module = importlib.import_module("opentelemetry.sdk.trace")
            export_module = importlib.import_module("opentelemetry.sdk.trace.export")
        except ModuleNotFoundError:
            logging.getLogger(get_logging_settings().logger_name).warning(
                "OpenTelemetry SDK is not installed; tracing is disabled"
            )
            return

        release = get_release_settings()
        resource = resource_module.Resource.create(
            {
                "service.name": settings.service_name,
                "service.version": release.release_version,
                "deployment.environment": release.environment,
            }
        )
        tracer_provider = sdk_trace_module.TracerProvider(resource=resource)
        if settings.otlp_endpoint:
            try:
                exporter_module = importlib.import_module(
                    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter"
                )
                exporter = exporter_module.OTLPSpanExporter(
                    endpoint=settings.otlp_endpoint
                )
                tracer_provider.add_span_processor(
                    export_module.BatchSpanProcessor(exporter)
                )
            except ModuleNotFoundError:
                logging.getLogger(get_logging_settings().logger_name).warning(
                    "OTLP exporter is not installed; tracing spans will not export"
                )

        trace_module.set_tracer_provider(tracer_provider)
        self._trace_module = trace_module
        self._tracer = trace_module.get_tracer(settings.service_name)
        self.enabled = True

    @contextmanager
    def span(
        self,
        name: str,
        *,
        attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[Any]:
        if self._tracer is None:
            with NoopTracingProvider().span(name, attributes=attributes) as span:
                yield span
            return

        with self._tracer.start_as_current_span(name) as span:
            for key, value in (attributes or {}).items():
                if value is not None:
                    span.set_attribute(key, value)
            try:
                yield span
            except Exception as exc:
                span.record_exception(exc)
                span.set_attribute("error", True)
                raise

    def instrument_fastapi(self, app: Any) -> None:
        if not self.enabled:
            return
        try:
            module = importlib.import_module("opentelemetry.instrumentation.fastapi")
            module.FastAPIInstrumentor.instrument_app(app)
        except Exception as exc:
            _log_observability_warning("fastapi tracing instrumentation failed", exc)

    def instrument_sqlalchemy(self, engine: Any) -> None:
        if not self.enabled:
            return
        try:
            module = importlib.import_module("opentelemetry.instrumentation.sqlalchemy")
            module.SQLAlchemyInstrumentor().instrument(engine=engine)
        except Exception as exc:
            _log_observability_warning("sqlalchemy tracing instrumentation failed", exc)

    def instrument_httpx(self) -> None:
        if not self.enabled:
            return
        try:
            module = importlib.import_module("opentelemetry.instrumentation.httpx")
            module.HTTPXClientInstrumentor().instrument()
        except Exception as exc:
            _log_observability_warning("httpx tracing instrumentation failed", exc)


tracing_provider: TracingProvider = NoopTracingProvider()


def configure_tracing(
    *, app: Any | None = None, sqlalchemy_engine: Any | None = None
) -> None:
    global tracing_provider

    provider = OpenTelemetryTracingProvider()
    provider.configure()
    if provider.enabled:
        if app is not None:
            provider.instrument_fastapi(app)
        if sqlalchemy_engine is not None:
            provider.instrument_sqlalchemy(sqlalchemy_engine)
        provider.instrument_httpx()
        tracing_provider = provider
    else:
        tracing_provider = NoopTracingProvider()


@contextmanager
def trace_span(
    name: str,
    **attributes: Any,
) -> Iterator[Any]:
    with tracing_provider.span(name, attributes=attributes) as span:
        yield span


def configure_logging() -> None:
    settings = get_logging_settings()
    logging.basicConfig(level=settings.log_level, force=False)
    logging.getLogger(settings.logger_name).setLevel(settings.log_level)


def log_event(
    event: str,
    *,
    status: str,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    settings = get_logging_settings()
    release = get_release_settings()
    logger = logging.getLogger(settings.logger_name)
    context = get_request_context()
    payload: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "service": "accessiq",
        "release": release.release_version,
        "version": release.release_version,
        "environment": release.environment,
        "git_sha": release.git_sha,
        "event": event,
        "status": status,
        **fields,
    }

    if context is not None:
        payload.setdefault("correlation_id", context.correlation_id)
        payload.setdefault("request_start", context.request_start.isoformat())
        payload.setdefault("client_ip", context.client_ip)
        payload.setdefault("user_agent", context.user_agent)
        payload.setdefault(
            "request",
            {
                "correlation_id": context.correlation_id,
                "start": context.request_start.isoformat(),
                "client_ip": context.client_ip,
                "user_agent": context.user_agent,
            },
        )
        if context.authenticated_user is not None:
            payload.setdefault(
                "authenticated_user_id",
                context.authenticated_user.id,
            )
            payload.setdefault(
                "authenticated_user_role",
                context.authenticated_user.operator_role,
            )
            payload.setdefault(
                "user",
                {
                    "id": context.authenticated_user.id,
                    "email": context.authenticated_user.email,
                    "role": context.authenticated_user.operator_role,
                },
            )

    logger.log(level, json.dumps(payload, default=str, sort_keys=True))


def record_http_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    normalized_path = normalize_request_path(path)
    labels = {
        "method": method,
        "path": normalized_path,
        "status_code": str(status_code),
    }
    metrics_registry.increment(
        "accessiq_http_requests_total",
        labels=labels,
        description="Total HTTP requests handled by AccessIQ.",
    )
    metrics_registry.observe(
        "accessiq_http_request_duration_seconds",
        duration_seconds,
        labels={"method": method, "path": normalized_path},
        description="HTTP request duration in seconds.",
    )
    if status_code >= 500:
        metrics_registry.increment(
            "accessiq_http_request_errors_total",
            labels=labels,
            description="Total HTTP requests returning server errors.",
        )
    if path.startswith("/scim"):
        metrics_registry.increment(
            "accessiq_scim_requests_total",
            labels=labels,
            description="Total SCIM API requests handled by AccessIQ.",
        )
    if path.startswith("/ai"):
        metrics_registry.increment(
            "accessiq_ai_requests_total",
            labels=labels,
            description="Total AI endpoint requests handled by AccessIQ.",
        )


def record_authentication(result: str) -> None:
    metrics_registry.increment(
        "accessiq_authentication_events_total",
        labels={"result": result},
        description="Authentication attempts grouped by result.",
    )


def record_rbac_denial(*, role: str, required_roles: list[str]) -> None:
    metrics_registry.increment(
        "accessiq_rbac_denials_total",
        labels={
            "role": role,
            "required_roles": ",".join(sorted(required_roles)),
        },
        description="API RBAC authorization denials.",
    )


def record_policy_denial(*, action: str) -> None:
    metrics_registry.increment(
        "accessiq_policy_denials_total",
        labels={"action": action},
        description="Business policy denials for access mutations.",
    )


def record_database_query(*, operation: str, status: str) -> None:
    metrics_registry.increment(
        "accessiq_database_queries_total",
        labels={"operation": operation, "status": status},
        description="Database operations recorded by AccessIQ.",
    )


def normalize_request_path(path: str) -> str:
    return re.sub(r"/[0-9]+(?=/|$)", "/{id}", path)


def _set_release_metrics() -> None:
    release = get_release_settings()
    metrics_registry.set_gauge(
        "accessiq_release_info",
        1,
        labels={
            "version": release.release_version,
            "environment": release.environment,
            "git_sha": release.git_sha,
            "helm_chart_version": release.helm_chart_version,
        },
        description="Release metadata for the running AccessIQ backend.",
    )


def _normalize_labels(labels: MetricLabels | None) -> LabelSet:
    if not labels:
        return ()
    return tuple(
        sorted(
            (str(key), str(value)) for key, value in labels.items() if value is not None
        )
    )


def _format_labels(labels: LabelSet) -> str:
    if not labels:
        return ""
    encoded = ",".join(f'{key}="{_escape_label_value(value)}"' for key, value in labels)
    return "{" + encoded + "}"


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _sanitize_metric_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_:]", "_", name)


def _render_metric_header(
    name: str,
    metric_type: str,
    descriptions: Mapping[str, str],
) -> list[str]:
    description = descriptions.get(name, name.replace("_", " "))
    return [
        f"# HELP {name} {description}",
        f"# TYPE {name} {metric_type}",
    ]


def _format_value(value: float) -> str:
    numeric_value = float(value)
    if numeric_value.is_integer():
        return str(int(numeric_value))
    return f"{numeric_value:.6f}".rstrip("0").rstrip(".")


def _format_bucket(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return str(value)


def _log_observability_warning(message: str, exc: Exception) -> None:
    logging.getLogger(get_logging_settings().logger_name).warning(
        "%s: %s",
        message,
        exc,
    )
