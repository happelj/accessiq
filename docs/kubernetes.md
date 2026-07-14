# Kubernetes And Helm

AccessIQ is packaged as a portable Kubernetes application through the Helm chart in `helm/accessiq`. The chart is cloud-agnostic and can be used with Docker Desktop Kubernetes, kind, minikube, AKS, GKE, or EKS after images are available to the target cluster.

The chart includes production-oriented hardening for the backend and frontend workloads while keeping local development values simple. It does not deploy AWS infrastructure, GitOps controllers, service meshes, external secret operators, or production PostgreSQL operations.

## Architecture

The Helm chart renders:

- Namespace
- ServiceAccount
- Backend Deployment and Service
- Frontend Deployment and Service
- Backend ConfigMap and Secret
- Frontend ConfigMap
- Optional development PostgreSQL Deployment, Service, Secret, and PVC
- Security contexts
- Rolling update strategy controls
- HorizontalPodAutoscalers
- PodDisruptionBudgets
- NetworkPolicies
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

## Production Hardening

The chart hardens the backend and frontend workloads with:

- pod-level `runAsNonRoot` settings
- container-level `allowPrivilegeEscalation: false`
- dropped Linux capabilities
- `seccompProfile: RuntimeDefault`
- read-only root filesystems for backend and frontend containers
- writable `emptyDir` scratch mounts for `/tmp` and Nginx cache paths
- soft pod anti-affinity
- soft topology spread constraints
- RollingUpdate deployment controls
- optional HPAs, PDBs, and NetworkPolicies

The backend image runs as UID/GID `10001`. The frontend production image uses the unprivileged Nginx image and listens on container port `8080`; the Kubernetes Service still exposes port `80`.

The bundled PostgreSQL deployment is for development only. It receives conservative security settings, but it is not intended to replace a managed database or production-grade PostgreSQL operator.

## Local Validation

Run these checks before deploying:

```bash
helm lint helm/accessiq
helm template accessiq helm/accessiq -f helm/accessiq/values-dev.yaml
helm template accessiq helm/accessiq -f helm/accessiq/values-prod.yaml
helm template accessiq helm/accessiq -f helm/accessiq/values-dev.yaml | kubectl apply --dry-run=client -f -
helm template accessiq helm/accessiq -f helm/accessiq/values-prod.yaml | kubectl apply --dry-run=client -f -
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

To validate the production-hardening resources on a local cluster without switching to production database values, enable them as overrides:

```bash
helm upgrade accessiq helm/accessiq \
  --namespace accessiq-dev \
  -f helm/accessiq/values-dev.yaml \
  --set namespace.create=false \
  --set networkPolicies.enabled=true \
  --set backend.autoscaling.enabled=true \
  --set frontend.autoscaling.enabled=true \
  --set backend.pdb.enabled=true \
  --set frontend.pdb.enabled=true
```

Then check:

```bash
kubectl -n accessiq-dev get pods,hpa,pdb,networkpolicy
```

Docker Desktop Kubernetes does not include metrics-server by default, so HPA targets may show `<unknown>`. Install metrics-server in clusters where CPU-based autoscaling should actively reconcile.

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

## Autoscaling

Backend and frontend HPAs are controlled independently:

```yaml
backend:
  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70

frontend:
  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70
```

When autoscaling is enabled, Helm does not render `spec.replicas` for that Deployment and the HPA owns replica count. Kubernetes metrics-server is required for CPU utilization metrics.

## Pod Disruption Budgets

Backend and frontend PDBs are disabled in development values and enabled in production values:

```yaml
backend:
  pdb:
    enabled: true
    minAvailable: 2

frontend:
  pdb:
    enabled: true
    minAvailable: 2
```

Use a `minAvailable` value that fits the configured minimum replica count. A PDB cannot preserve availability if a workload only has one pod.

## Network Policies

NetworkPolicies are enabled by default in base values, disabled in `values-dev.yaml`, and enabled in `values-prod.yaml`.

Rendered policies include:

- default deny ingress and egress for AccessIQ pods
- frontend HTTP ingress
- frontend egress to backend
- backend HTTP ingress
- backend DNS egress
- backend egress to internal PostgreSQL when the development database is enabled
- backend egress to an external database when configured
- optional backend HTTPS egress for provider APIs or external connectors
- PostgreSQL ingress from backend only when internal PostgreSQL is enabled

Production external database egress is intentionally configurable:

```yaml
networkPolicies:
  backend:
    externalDatabaseEgress:
      enabled: true
      cidr: 0.0.0.0/0
      port: 5432
```

Replace `0.0.0.0/0` with the managed database CIDR or private network range for the target cluster.

Ingress controller source restrictions are cluster-specific. The default policies allow HTTP ingress to backend and frontend pods so common Nginx, cloud load balancer, and local ingress-controller layouts keep working. Tighten ingress sources with cluster-specific selectors once the ingress controller namespace and pod labels are known.

## Rolling Updates And Scheduling

Backend and frontend Deployments use configurable RollingUpdate settings:

```yaml
deploymentStrategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 0
    maxSurge: 1
minReadySeconds: 10
progressDeadlineSeconds: 600
```

Soft pod anti-affinity and topology spread constraints prefer distributing replicas across nodes while remaining compatible with one-node local clusters.

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

When `database.internal.enabled=false`, configure `database.external.url` and the matching network policy egress values.

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

## Production Values

`values-prod.yaml` is a starting point for managed Kubernetes platforms:

- internal PostgreSQL disabled
- external PostgreSQL URL placeholder
- backend and frontend replicas set for HA
- HPAs enabled for backend and frontend
- PDBs enabled for backend and frontend
- NetworkPolicies enabled
- production resource requests and limits
- TLS ingress placeholder
- production image repository placeholders under `ghcr.io/happelj`

Before deploying production values, replace image tags, database URL, secrets, ingress host, TLS secret, and network policy CIDRs.

## Troubleshooting

- `ImagePullBackOff`: build and tag local images for Docker Desktop, or push images to a registry reachable by the cluster.
- HPA `TARGETS <unknown>`: install metrics-server or disable autoscaling in local values.
- Pods fail with non-root errors: rebuild images after the Dockerfile hardening changes.
- Frontend readiness fails: confirm the image listens on container port `8080` and the Service targets the named `http` port.
- Read-only filesystem errors: add a specific `emptyDir` mount for the path that needs runtime writes; do not disable read-only root filesystem unless necessary.
- Backend database connection errors: verify `DATABASE_URL`, the database Secret, and NetworkPolicy egress to PostgreSQL.
- Ingress not routing: verify ingress controller installation, `ingress.className`, DNS or hosts file entries, and host/path rules.

## Future Production Roadmap

Future milestones can add:

- image publishing to a registry
- runtime frontend configuration
- Kubernetes readiness for external managed PostgreSQL
- migrations as Jobs
- external secret integration
- AWS EKS-specific values
- GitOps deployment automation
