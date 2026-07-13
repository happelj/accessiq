# ADR 0010: In-Process Domain Events

## Status

Accepted

## Context

AccessIQ publishes events for provisioning, governance, remediation, delegation, and connector activity, but it does not yet require durable event infrastructure.

## Decision

Use an in-process domain event publisher. Events remain inspectable in tests, and publication increments lightweight metrics.

## Alternatives Considered

- Add a durable event broker. This was rejected because the current project runs synchronously and locally.
- Remove domain events until deployment. This was rejected because events document extension points for future workers and integrations.

## Consequences

The design documents event boundaries without introducing a broker. Future durable eventing can subscribe at the same service boundaries and replace the publisher implementation.
