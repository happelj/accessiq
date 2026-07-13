# ADR 0006: Expanded Health Response

## Status

Accepted

## Context

`/health` previously returned only `{"status": "healthy"}`. That was insufficient once connectors, audit, provisioning, domain events, and configuration became first-class concerns.

## Decision

Return a structured health response with top-level status, correlation ID, subsystem details, and metrics.

## Alternatives Considered

- Keep the original `{"status": "healthy"}` response. This was rejected because it hides connector, audit, provisioning, domain event, and configuration state.
- Add separate health endpoints per subsystem. This was rejected as unnecessary for the current API size.

## Consequences

The endpoint remains public and simple to call, but it now provides enough detail for manual and automated validation. Database failure still returns `503` because database reachability is critical.
