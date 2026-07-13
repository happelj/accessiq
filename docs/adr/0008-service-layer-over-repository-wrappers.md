# ADR 0008: Service Layer Over Repository Wrappers

## Status

Accepted

## Context

The architecture review considered repositories, but the codebase already has service classes that own meaningful query, validation, mutation, audit, and event behavior.

## Decision

Do not add generic repository wrappers during Milestone 10. Keep query behavior in services unless a future module shows real duplication or a need for alternate storage.

## Alternatives Considered

- Wrap every SQLAlchemy model in a repository. This was rejected because it would create boilerplate without reducing present complexity.
- Move all SQLAlchemy access back into routes. This was rejected because services already provide clearer business boundaries.

## Consequences

The code avoids extra indirection. If persistence complexity grows, repositories can be introduced for specific aggregates instead of as a broad pattern.
