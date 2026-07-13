# ADR 0003: Request Context And Correlation ID

## Status

Accepted

## Context

Audit events, provisioning jobs, connector results, and domain events already used correlation IDs in some paths, but there was no reusable request-level context.

## Decision

Create a request context backed by `contextvars`. Middleware resolves `X-Correlation-ID`, request start, client IP, and user agent. Authentication enriches the context with authenticated user metadata.

## Alternatives Considered

- Pass correlation IDs through every function signature. This was rejected because it would add repetitive plumbing across unrelated services.
- Store request state in module globals. This was rejected because concurrent requests need isolation.

## Consequences

Every HTTP response includes `X-Correlation-ID`. Audit and provisioning flows can inherit request correlation when no operation-specific ID is supplied. Non-request code still works because context lookup is optional.
