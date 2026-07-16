# Release Engineering

Milestone 15C adds release metadata, deployment history, and progressive delivery support around the existing AccessIQ deployment path. It does not change application functionality, Terraform resource design, or the Kubernetes architecture.

## Release Lifecycle

AccessIQ releases follow this lifecycle:

```text
Git commit or tag
  -> GitHub Actions workflow_dispatch
  -> backend and frontend validation
  -> Docker image build with OCI labels
  -> ECR push with immutable image tag
  -> ECR image digest lookup
  -> Helm render and upgrade
  -> rollout verification
  -> smoke tests
  -> application release metadata visible through the API
```

The AWS deployment workflow remains manual. A release is deployed only when an operator runs the `Deploy AWS` workflow.

## Release Metadata

The backend reads release metadata from environment variables populated by Helm:

```text
ACCESSIQ_VERSION
ACCESSIQ_ENVIRONMENT
ACCESSIQ_GIT_SHA
ACCESSIQ_GIT_TAG
ACCESSIQ_BUILD_TIMESTAMP
ACCESSIQ_DOCKER_IMAGE
ACCESSIQ_IMAGE_DIGEST
ACCESSIQ_HELM_CHART_VERSION
ACCESSIQ_HELM_REVISION
ACCESSIQ_TERRAFORM_VERSION
ACCESSIQ_DEPLOYMENT_OPERATOR
ACCESSIQ_DEPLOYMENT_STATUS
ACCESSIQ_DEPLOYED_AT
```

The Helm chart exposes these values through `release` values in `helm/accessiq/values.yaml`. The AWS workflow overrides them at deploy time.

The backend and frontend Docker images also receive OCI image labels:

```text
org.opencontainers.image.version
org.opencontainers.image.revision
org.opencontainers.image.ref.name
org.opencontainers.image.created
```

## Version API

`GET /version` is public and returns the current release metadata:

```bash
curl http://localhost:8000/version
```

Example fields:

```json
{
  "service": "AccessIQ",
  "version": "f3c1e2a4b5d6",
  "environment": "dev",
  "git_sha": "f3c1e2a4b5d6...",
  "git_tag": null,
  "build_timestamp": "2026-07-16T12:00:00Z",
  "docker_image": "123456789012.dkr.ecr.us-east-1.amazonaws.com/accessiq-dev-backend:f3c1e2a4b5d6",
  "image_digest": "sha256:...",
  "helm_chart_version": "0.1.0",
  "terraform_version": ">= 1.10.0, < 2.0.0"
}
```

## Release APIs

Release history endpoints require a `security_admin`, `iam_admin`, or `auditor` bearer token:

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/releases
curl -H "Authorization: Bearer <token>" http://localhost:8000/releases/current
```

`GET /releases` returns deployment records newest first and supports:

```text
environment
status
start_index
count
```

`GET /releases/current` returns current release metadata plus the latest deployment record for the runtime environment.

## Deployment History

Deployment history is stored in the application database in `release_deployments`. It is intentionally lightweight and does not require Kubernetes API persistence.

Each record tracks:

- environment
- deployment time
- version
- Git SHA and tag
- build timestamp
- Docker image and image digest
- Helm chart version and Helm revision
- Terraform version constraint
- operator
- deployment status

On application startup, AccessIQ records the current deployment idempotently from environment metadata. Restarting the same release does not create duplicate records for the same version, Git SHA, operator, status, image, and Helm revision.

## Helm Operations

Check release status:

```bash
helm status accessiq --namespace accessiq
```

View release history:

```bash
helm history accessiq --namespace accessiq
```

Upgrade with release metadata:

```bash
helm upgrade --install accessiq helm/accessiq \
  --namespace accessiq \
  -f helm/accessiq/values-aws.yaml \
  --set-string release.version=<git-sha-or-tag> \
  --set-string release.gitSha=<git-sha> \
  --set-string release.buildTimestamp=<utc-build-time> \
  --set-string release.dockerImage=<backend-image> \
  --set-string release.imageDigest=<backend-image-digest> \
  --set-string release.environment=dev \
  --wait \
  --timeout 10m
```

Roll back to the previous revision:

```bash
helm rollback accessiq --namespace accessiq
```

Roll back to a specific revision:

```bash
helm rollback accessiq <revision> --namespace accessiq
```

After rollback, verify:

```bash
helm status accessiq --namespace accessiq
kubectl -n accessiq rollout status deployment/accessiq-backend
kubectl -n accessiq rollout status deployment/accessiq-frontend
curl https://<host>/version
```

## Smoke Tests

The AWS smoke test validates:

- `/health`
- `/version`
- frontend root `/`
- `/openapi.json`
- `POST /login`
- authenticated AI provider status
- authenticated SCIM metadata
- authenticated graph cache status
- authenticated connectors
- authenticated provisioning jobs
- authenticated access reviews
- authenticated remediation jobs
- authenticated current release metadata

Run manually:

```bash
ACCESSIQ_BASE_URL=https://<host> bash scripts/aws-smoke-test.sh
```

## Manual Validation

Local API checks:

```bash
curl http://localhost:8000/version
```

PowerShell authenticated checks:

```powershell
$login = Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/login `
  -ContentType "application/json" `
  -Body '{"email":"alice@example.com","password":"Password123!"}'

$headers = @{ Authorization = "Bearer $($login.access_token)" }

Invoke-RestMethod -Method Get -Uri http://localhost:8000/releases -Headers $headers
Invoke-RestMethod -Method Get -Uri http://localhost:8000/releases/current -Headers $headers
```

Chart validation:

```bash
helm lint helm/accessiq -f helm/accessiq/values-aws.yaml
helm template accessiq helm/accessiq -f helm/accessiq/values-aws.yaml
```
