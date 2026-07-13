# ADR 0005: Lightweight Process Metrics

## Status

Accepted

## Context

The milestone asks for metrics but explicitly avoids a Prometheus integration.

## Decision

Add a thread-safe in-memory counter registry for request, audit, connector, retry, and domain event counts. Expose the current snapshot in `/health`.

## Alternatives Considered

- Add Prometheus immediately. This was rejected because the milestone explicitly avoids external metrics systems.
- Skip metrics until deployment. This was rejected because connector and request counters are useful for local validation now.

## Consequences

Local validation can inspect operational counters without a metrics server. Counters are process-local and reset on restart, so they are not a durable analytics store.
