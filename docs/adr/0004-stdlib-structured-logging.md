# ADR 0004: Standard-Library Structured Logging

## Status

Accepted

## Context

The project needs observable behavior without adding a logging framework or external service.

## Decision

Use Python standard-library logging and emit JSON payloads from `app/observability.py`.

## Alternatives Considered

- Keep free-form log messages. This was rejected because correlation and operational fields would be inconsistent.
- Adopt an external logging library. This was rejected because the milestone requires standard-library compatibility.

## Consequences

Logs are machine-readable and include request context when available. The implementation remains dependency-light and can later be redirected to a production log collector.
