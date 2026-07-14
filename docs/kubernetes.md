# Kubernetes And Helm

Milestone 14A packages AccessIQ as a portable Kubernetes application. Helm is the primary deployment mechanism. The chart is cloud-agnostic and can be used with Docker Desktop Kubernetes, kind, minikube, AKS, GKE, or EKS after images are available to the target cluster.

This milestone does not add AWS deployment, GitOps, autoscaling, service mesh configuration, or production PostgreSQL operations.

## Architecture

The Helm chart renders:

- Namespace
- ServiceAccount
- Backend Deployment and Service
- Frontend Deployment and Service
- Backend ConfigMap and Secret
- Frontend ConfigMap
- Optional development PostgreSQL Deployment, Service, Secret, and PVC
- Frontend Ingress
- Backend API and Swagger Ingress
- Helm test pod for the backend health endpoint

```text
Ingress Host
  -> /                  -> Frontend Service -> Frontend Pods
  -> /docs, /openapi... -> Backend Service  -> Backend Pods
  -> API route prefixes -> Backend Service  -> Backend Pods
                                       |
                                       -> PostgreSQL Service -> PostgreSQL Pod
```

The default chart enables a development PostgreSQL deployment. Production deployments should use a managed database or a production-grade PostgreSQL operator/chart.

## Chart Layout

```text
helm/accessiq/
  Chart.yaml
  values.yaml
  values-dev.yaml
  values-prod.yaml
  templates/
```

Use `values-dev.yaml` for local clusters and `values-prod.yaml` as a production-oriented starting point.

## Local Validation

Run these checks before deploying:

```bash
helm lint helm/accessiq
helm template accessiq helm/accessiq -f helm/accessiq/values-dev.yaml
helm template accessiq helm/accessiq -f helm/accessiq/values-dev.yaml | kubectl apply --dry-run=client -f -
```

PowerShell users can use the same commands.

The GitHub Actions CI workflow also runs Helm linting, renders development and production values, creates a disposable kind cluster for API discovery, and validates the rendered manifests with `kubectl apply --dry-run=client`.

## Local Deployment

Build images that the local cluster can access. For Docker Desktop Kubernetes, locally tagged images usually work:

```bash
docker build -t accessiq-api:latest .
docker build -t accessiq-frontend:latest frontend
```

Install or upgrade the chart:

```bash
helm upgrade --install accessiq helm/accessiq \
  --namespace accessiq-dev \
  --create-namespace \
  -f helm/accessiq/values-dev.yaml
```

Check the deployment:

```bash
kubectl -n accessiq-dev get pods
kubectl -n accessiq-dev get services
kubectl -n accessiq-dev get ingress
```

Port-forward the API health endpoint:

```bash
kubectl -n accessiq-dev port-forward svc/accessiq-backend 8000:8000
curl http://localhost:8000/health
```

Run the Helm test:

```bash
helm test accessiq --namespace accessiq-dev
```

## Upgrade

Update values or image tags, then run:

```bash
helm upgrade accessiq helm/accessiq \
  --namespace accessiq-dev \
  -f helm/accessiq/values-dev.yaml
```

View release history:

```bash
helm history accessiq --namespace accessiq-dev
```

## Rollback

Roll back to the previous revision:

```bash
helm rollback accessiq --namespace accessiq-dev
```

Roll back to a specific revision:

```bash
helm rollback accessiq 2 --namespace accessiq-dev
```

## ConfigMaps

Non-sensitive backend configuration is rendered into a ConfigMap:

- JWT algorithm
- token lifetime
- AI enablement and provider settings
- model names
- CORS settings
- logging settings
- connector enablement flags and base URLs

The frontend ConfigMap exposes `VITE_API_BASE_URL`. The current Vite frontend reads this at build time, so production frontend images should be built with the intended API URL until runtime frontend configuration is added.

## Secrets

The chart creates placeholder Secrets only when an existing Secret is not supplied. Never commit real values.

Sensitive values include:

- `DATABASE_URL`
- `JWT_SECRET`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- development PostgreSQL password

For production, prefer pre-created Kubernetes Secrets, a sealed secret workflow, or an external secret operator. Set `backend.secrets.existingSecret` and match the configured key names when using an existing Secret.

## PostgreSQL And PVC

`database.internal.enabled=true` deploys a simple PostgreSQL container and PVC for development. This is useful for Docker Desktop, kind, and minikube validation.

Production should set:

```yaml
database:
  external:
    url: postgresql+psycopg://accessiq:replace-me@postgres.example.com:5432/accessiq
  internal:
    enabled: false
```

Use a managed database or production-grade PostgreSQL deployment with backups, monitoring, upgrades, replication, and disaster recovery.

## Ingress

The chart creates separate frontend and backend Ingress resources for the same host. This lets `/` serve the React app while API and Swagger paths route to the backend.

Default backend paths include:

- `/docs`
- `/redoc`
- `/openapi.json`
- `/health`
- `/login`
- `/users`
- `/applications`
- `/access`
- `/scim`
- `/connectors`
- `/provisioning`
- `/access-reviews`
- `/remediation`
- `/delegation`
- `/graph`
- `/ai`

The default ingress class is `nginx`. Update `ingress.className`, `ingress.host`, annotations, and TLS values for the target cluster.

## Future Production Roadmap

Future milestones can add:

- image publishing to a registry
- runtime frontend configuration
- Kubernetes readiness for external managed PostgreSQL
- migrations as Jobs
- horizontal pod autoscaling
- network policies
- pod disruption budgets
- external secret integration
- AWS EKS-specific values
- GitOps deployment automation
