# ADR 0002: Centralized Configuration Providers

## Status

Accepted

## Context

Environment variables were mostly centralized, but database setup still read `DATABASE_URL` directly. More settings are expected as connectors and observability mature.

## Decision

Centralize runtime configuration in `app/config.py` using cached provider functions for authentication, database, connector, and logging settings.

## Alternatives Considered

- Continue reading environment variables inside individual modules. This was rejected because it makes configuration harder to audit.
- Add a full settings framework. This was rejected because the current settings surface is small and does not justify the extra dependency.

## Consequences

Environment access is easy to audit and override in tests. Modules depend on typed settings objects instead of scattered `os.getenv` calls.
