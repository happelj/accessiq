# ADR 0001: Layered FastAPI Service Boundaries

## Status

Accepted

## Context

AccessIQ includes native REST endpoints, SCIM protocol endpoints, access policy, audit, connectors, provisioning history, governance, remediation, and delegation. Route handlers were at risk of becoming the place where every concern met.

## Decision

Keep FastAPI routes thin. Routes authenticate, authorize, parse inputs, map service errors to HTTP responses, and commit or roll back request transactions. Business behavior belongs in services, policy modules, connector orchestration, and protocol-specific helpers.

## Alternatives Considered

- Put business logic directly in routes. This was rejected because route modules would become harder to test and reuse.
- Move all behavior into one application service. This was rejected because SCIM, governance, remediation, delegation, and connectors have different protocol and domain boundaries.

## Consequences

The API remains easier to test because services can be exercised without HTTP. Route modules still own HTTP response semantics, which keeps protocol details out of the service layer.
