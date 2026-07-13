# ADR 0009: Synchronous Provisioning Orchestration

## Status

Accepted

## Context

Connector execution, retries, provisioning jobs, history, audit, and remediation all need deterministic behavior for local validation. A worker queue would add operational complexity before it is needed.

## Decision

Keep `ProvisioningOrchestrator` synchronous. It records jobs and history when a database session is provided, retries immediately according to policy, and returns a `ConnectorResult`.

## Alternatives Considered

- Add a queue and worker now. This was rejected because the app does not yet need operational queue infrastructure.
- Run connector operations directly from remediation without an orchestrator. This was rejected because retry, history, audit, and event behavior would be duplicated.

## Consequences

Tests remain deterministic and manual validation is direct. The persisted job/history model leaves a clear path for a future scheduler or durable worker.
