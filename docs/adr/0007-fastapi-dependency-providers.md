# ADR 0007: FastAPI Dependency Providers

## Status

Accepted

## Context

Several route modules constructed connector registries or services directly. The pattern was repetitive and made future constructor changes harder.

## Decision

Add `app/dependencies.py` with provider functions for connector registry, provisioning orchestrator, provisioning job service, governance services, remediation service, and delegation service.

## Alternatives Considered

- Keep constructing services directly inside every route. This was rejected because constructor changes would require broad route edits.
- Introduce a separate dependency injection container. This was rejected because FastAPI already provides the needed request-scoped composition model.

## Consequences

Route modules share construction logic and tests can still instantiate services directly. Dependency injection is limited to composition; it does not move business behavior into providers.
