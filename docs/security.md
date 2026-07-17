# Security And Production Readiness

Milestone 16C documents the AccessIQ security posture for a Version 1.0-style
release candidate. It does not redesign product behavior, deployment topology,
Kubernetes packaging, or AWS infrastructure. It records current controls,
production checks, and residual risks that should be accepted or remediated
before a real customer deployment.

## Security Review Summary

| Area | Current Control | Production Readiness Notes |
| --- | --- | --- |
| Authentication | JWT bearer authentication with Argon2 password hashes. Tokens include `sub`, `iat`, and `exp`. | Use a strong externally supplied `JWT_SECRET`. Rotate on incident or operator change. |
| API authorization | Protected routes use reusable RBAC dependencies. Business policy and delegation checks run after endpoint authorization. | Public demo endpoints should be reviewed before internet exposure, especially user listing and user creation. |
| Delegation | Scoped delegated access actions are time bounded and still pass through the business policy engine. | Add administrative reporting and scheduled expiry review for production operations. |
| SCIM | SCIM read/provisioning routes require `security_admin` or `iam_admin` and return SCIM-shaped errors. | Put SCIM endpoints behind identity-provider-specific network allow lists when possible. |
| AI | AI routes require admin/auditor roles, use deterministic evidence retrieval, and do not make access decisions. | Treat prompts and evidence as sensitive identity data. Keep provider keys in Secrets Manager or Kubernetes Secrets. |
| Provisioning | Connector execution is tracked in jobs/history with correlation IDs and audit events. Mock connectors do not call external systems. | Real connectors must add credential isolation, rate limiting, and outbound network restrictions. |
| Reviews and remediation | Access review mutation routes are role protected. Remediation uses existing provisioning history. | Require approval workflow and background job durability before high-scale production use. |
| Graph | Authorization graph routes are role protected and read-only. | Treat graph exports as sensitive because they summarize identity relationships. |
| Connectors | Connector metadata and health routes are role protected. Current connectors are deterministic mocks. | Real connector credentials must never be stored in config maps or committed files. |
| Observability | `/metrics`, `/health`, and `/version` support operational validation. Structured logs include correlation IDs. | Restrict `/metrics` and API docs at ingress or network layer in production. |
| HTTP headers | Backend and frontend now set CSP, HSTS, Referrer-Policy, Permissions-Policy, X-Content-Type-Options, and X-Frame-Options. | HSTS only takes effect over HTTPS. Production ingress must terminate TLS. |
| Kubernetes | Helm defaults include non-root pods, dropped Linux capabilities, disabled service account token automount, resource limits, probes, PDB/HPA options, and NetworkPolicies. | Use managed PostgreSQL for production and validate NetworkPolicy enforcement in the target CNI. |
| AWS | Terraform uses private subnets, private RDS, encrypted RDS storage, managed master password, EKS OIDC, ECR, and scoped GitHub OIDC deploy role. | Tighten EKS public endpoint CIDRs and add WAF, KMS customer-managed keys, and runtime security controls as needed. |

## Production Checklist

- Replace all development placeholders in `.env`, Helm values, and AWS Secrets
  Manager before deployment.
- Use a high-entropy `JWT_SECRET` stored in Kubernetes Secret or AWS Secrets
  Manager, not in Git.
- Deploy through HTTPS only and configure ingress TLS certificates.
- Restrict `/metrics`, `/docs`, `/redoc`, and `/openapi.json` to internal or
  trusted administrative networks for production.
- Configure CORS to the exact production frontend origin.
- Run backend tests, frontend tests, Docker builds, Helm validation, Terraform
  validation, dependency audits, secret scan, container scan, and k6 smoke tests.
- Generate and archive SBOMs for Python, Node, backend image, and frontend image.
- Review Trivy results for backend and frontend images before release.
- Review Gitleaks output before merge.
- Review GitHub dependency review findings on pull requests.
- Configure branch protection to require all CI security jobs.
- Use managed PostgreSQL or a production-grade PostgreSQL operator.
- Confirm NetworkPolicies are enforced by the Kubernetes CNI.
- Configure log retention and access controls for application logs.
- Configure backup, restore, and RDS deletion protection for non-demo
  environments.
- Confirm EKS node, pod, and deployment IAM permissions are least privilege.
- Keep image tags immutable and record image digests in release metadata.

## Credential Rotation

Rotate credentials when an operator leaves, an integration is disabled, an
environment is rebuilt, or a secret may have been exposed.

Recommended rotation order:

1. Generate the replacement secret in the system of record.
2. Store it in AWS Secrets Manager or the target secret manager.
3. Update the Kubernetes Secret or external secret reference.
4. Restart affected deployments with a rolling rollout.
5. Verify `/health`, login, connector health, and smoke tests.
6. Revoke the old credential from the upstream provider.
7. Record the rotation in an operational change log.

JWT secret rotation invalidates existing access tokens. For a production
multi-secret rotation model, add a `kid` header and accept old signing keys for a
bounded overlap window.

## Secrets Management

Development defaults are for local validation only. Production secrets should be
managed outside the repository:

- AWS Secrets Manager for database URLs, JWT secrets, and AI provider keys.
- Kubernetes Secrets or External Secrets Operator for runtime injection.
- GitHub Actions OIDC for AWS access instead of long-lived AWS keys.
- Short-lived provider tokens where supported.

Never commit `.env`, provider API keys, database passwords, private keys, kubeconfig
files, Terraform state, or generated credentials.

## Incident Response

Initial response checklist:

1. Triage the alert and identify affected environment, release, image digest,
   and Git SHA.
2. Preserve logs, audit events, Kubernetes events, and relevant CI artifacts.
3. Revoke or rotate suspected credentials.
4. Disable affected provider integrations or ingress paths when containment is
   required.
5. Redeploy a known-good image or roll forward with a patched image.
6. Verify login, protected API access, SCIM, provisioning, reviews, remediation,
   graph, AI, health, and metrics.
7. Document root cause, blast radius, remediation, and follow-up controls.

Use correlation IDs from API responses and logs to tie user-facing failures to
audit events, connector activity, provisioning history, and request metrics.

## Supply Chain Controls

AccessIQ uses these validation layers:

- Python dependency audit: `bash scripts/python-dependency-audit.sh`
- JavaScript dependency audit: `npm --prefix frontend audit --audit-level=moderate`
- Secret scanning: `bash scripts/secret-scan.sh`
- SBOM generation: `bash scripts/generate-sbom.sh`
- Container scanning: `bash scripts/container-scan.sh accessiq-api:ci accessiq-frontend:ci`
- GitHub dependency review on pull requests.

Generated SBOM files are not committed by default because they are release
artifacts. CI uploads them as build artifacts. Local runs write to `sbom/`.

## Container Scanning

Build images first:

```bash
docker build -t accessiq-api:ci .
docker build -t accessiq-frontend:ci frontend
```

Scan images and generate image SBOMs:

```bash
bash scripts/container-scan.sh accessiq-api:ci accessiq-frontend:ci
```

The script prefers a local `trivy` binary and falls back to the
`aquasec/trivy:0.56.2` container image. By default, fixed high and critical image
findings fail the scan. Override severity for investigation with:

```bash
TRIVY_SEVERITY=CRITICAL bash scripts/container-scan.sh accessiq-api:ci accessiq-frontend:ci
```

## Secret Scanning

Run:

```bash
bash scripts/secret-scan.sh
```

The script prefers a local `gitleaks` binary and falls back to the
`zricethezav/gitleaks:v8.21.2` container image. `.gitleaks.toml` allow-lists
documented local demo placeholders and seed credentials so real findings remain
visible.

## SBOM Generation

Install the Python SBOM generator once:

```bash
python -m pip install cyclonedx-bom
```

Generate Python and Node CycloneDX SBOMs:

```bash
bash scripts/generate-sbom.sh
```

Container image SBOMs are generated by `scripts/container-scan.sh` with Trivy.

## Security Headers

Backend API responses and frontend static responses set:

- `Content-Security-Policy`
- `Strict-Transport-Security`
- `Referrer-Policy`
- `Permissions-Policy`
- `X-Content-Type-Options`
- `X-Frame-Options`

The backend CSP allows the FastAPI documentation assets from jsDelivr so local
Swagger UI remains usable. The frontend CSP allows local API calls to
`localhost:8000` and `127.0.0.1:8000` for development. Production deployments
should prefer same-origin API routing or a single explicit API origin.

Deferred headers:

- `Cross-Origin-Opener-Policy`, `Cross-Origin-Embedder-Policy`, and
  `Cross-Origin-Resource-Policy` are deferred until frontend asset and API
  embedding requirements are finalized.
- Cookie hardening is deferred because AccessIQ currently uses bearer tokens
  rather than session cookies.

## Kubernetes Review

Current chart strengths:

- ServiceAccount token automount disabled by default.
- Pods run as non-root users.
- Containers drop all Linux capabilities.
- Privilege escalation is disabled.
- Backend and frontend use read-only root filesystems.
- RuntimeDefault seccomp profiles are configured.
- Resource requests and limits are set.
- Probes, rolling update controls, optional HPAs, and optional PDBs are present.
- NetworkPolicies enforce default-deny behavior when supported by the CNI.
- Secrets are separated from ConfigMaps, and existing secret references are
  supported for production values.

Recommendations:

- Use a production CNI that enforces NetworkPolicies.
- Restrict ingress to TLS-only public endpoints.
- Use external secrets integration for cloud-managed secret stores.
- Keep development PostgreSQL disabled in production.
- Add admission controls such as Pod Security Admission, Kyverno, or Gatekeeper
  for production clusters.

## AWS Review

Current Terraform strengths:

- EKS nodes run in private subnets.
- RDS PostgreSQL is private, encrypted, and uses managed master password storage.
- EKS OIDC provider supports IAM roles for service accounts.
- GitHub Actions deploy role uses OIDC instead of static AWS keys.
- ECR repositories are environment scoped.
- Security groups restrict PostgreSQL ingress to configured source security
  groups.

Recommendations:

- Restrict EKS public endpoint CIDRs for production or use private endpoint
  access where operations allow it.
- Add AWS WAF for public ingress.
- Consider customer-managed KMS keys for RDS, Secrets Manager, and ECR.
- Add AWS Config, GuardDuty, CloudTrail retention, and EKS audit log retention.
- Scope GitHub OIDC subject claims to protected branches/tags for production.

## Release Signing Preparation

AccessIQ is ready for future Cosign/Sigstore signing, but signing is not required
for normal builds yet.

Future release flow:

1. Build immutable backend and frontend images.
2. Push images to ECR.
3. Resolve image digests.
4. Generate image SBOMs.
5. Sign image digests with Cosign keyless signing through GitHub OIDC.
6. Attach attestations for SBOM and provenance.
7. Verify signatures before Helm deployment.

## Residual Risks

- Development seed users and default passwords are intentionally present for
  local demos.
- Some read and user creation endpoints remain public to preserve current demo
  behavior.
- The bundled PostgreSQL deployment is not a production database pattern.
- Real connector credentials and connector rate limiting are future work.
- The AI provider layer depends on external provider controls when non-mock
  providers are enabled.
- Runtime container monitoring and admission-policy enforcement are documented
  but not bundled.
