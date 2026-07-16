# AWS Deployment

Milestone 15B adds a reproducible AWS deployment path for AccessIQ. It builds backend and frontend images, pushes immutable tags to Amazon ECR, deploys the existing Helm chart to Amazon EKS, verifies rollout, and runs smoke tests.

This deployment path is additive. Local Docker Compose, local Kubernetes, and the existing CI workflow remain unchanged.

## Architecture

```text
GitHub workflow_dispatch
  -> GitHub Actions OIDC
  -> AWS IAM role
  -> Backend and frontend tests
  -> Docker build
  -> Amazon ECR push
  -> aws eks update-kubeconfig
  -> Helm upgrade/install to EKS
  -> Kubernetes rollout checks
  -> HTTP smoke tests
```

AWS infrastructure is still managed by Terraform under `infrastructure/terraform`. The deployment workflow assumes that EKS, ECR, RDS, IAM, and Secrets Manager resources already exist.

## Workflow

The deployment workflow lives at `.github/workflows/deploy-aws.yml`.

It is intentionally manual:

```text
Actions -> Deploy AWS -> Run workflow
```

It does not automatically deploy every push to `main`.

Required workflow inputs:

- `environment`: `dev` or `prod`.
- `aws_region`: AWS region for ECR and EKS.
- `aws_role_arn`: IAM role assumed through GitHub OIDC.
- `eks_cluster_name`: target EKS cluster.
- `namespace`: Kubernetes namespace.
- `release_name`: Helm release name.
- `ingress_host`: public DNS host for AccessIQ.
- `backend_secret_name`: existing Kubernetes Secret used by the backend.

Optional inputs:

- `frontend_api_base_url`: defaults to `https://<ingress_host>`.
- `image_tag`: defaults to the Git SHA.
- `alb_certificate_arn`: optional ACM certificate ARN for HTTPS on the AWS Load Balancer Controller.
- `smoke_base_url`: defaults to `https://<ingress_host>`.
- `run_smoke_tests`: controls post-deploy smoke tests.

## GitHub OIDC

The workflow uses GitHub OIDC through:

```yaml
permissions:
  contents: read
  id-token: write
```

No long-lived AWS access keys are required.

The IAM trust policy should restrict the role to this repository. A tighter trust policy can also restrict by GitHub environment:

```json
{
  "Effect": "Allow",
  "Principal": {
    "Federated": "arn:aws:iam::<account-id>:oidc-provider/token.actions.githubusercontent.com"
  },
  "Action": "sts:AssumeRoleWithWebIdentity",
  "Condition": {
    "StringEquals": {
      "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
    },
    "StringLike": {
      "token.actions.githubusercontent.com:sub": "repo:happelj/accessiq:environment:dev"
    }
  }
}
```

Use a separate role or separate condition for `prod`.

## IAM Requirements

The GitHub Actions role needs AWS permissions for image publishing and cluster discovery:

- `ecr:GetAuthorizationToken` on `*`
- `ecr:DescribeRepositories`
- `ecr:BatchCheckLayerAvailability`
- `ecr:InitiateLayerUpload`
- `ecr:UploadLayerPart`
- `ecr:CompleteLayerUpload`
- `ecr:PutImage`
- `eks:DescribeCluster`

The role must also be authorized inside the EKS cluster through an EKS access entry or the `aws-auth` ConfigMap with Kubernetes RBAC that can:

- create namespaces when missing
- read Secrets in the target namespace
- install and upgrade Helm-managed resources
- get, list, create, update, patch, and delete Deployments, Services, ConfigMaps, Secrets, Ingresses, HPAs, PDBs, NetworkPolicies, and ServiceAccounts in the target namespace
- read pods, services, deployments, and ingress resources for rollout verification

The Terraform IAM module includes the AWS-side role and ECR/EKS policy path when GitHub OIDC is enabled. Kubernetes RBAC binding is still cluster configuration and must be created for the target environment.

## ECR

Terraform creates ECR repositories named by environment:

```text
accessiq-dev-backend
accessiq-dev-frontend
accessiq-prod-backend
accessiq-prod-frontend
```

The workflow derives repository URLs from the AWS account ID, region, and selected environment.

Images are tagged with an immutable tag:

- workflow `image_tag` input, when supplied
- otherwise the Git SHA

Do not rely on `latest` for AWS deployment.

## Helm Values

AWS-specific values live in:

```text
helm/accessiq/values-aws.yaml
```

The file configures:

- ECR image placeholders
- external RDS mode
- existing backend Secret
- AWS Load Balancer Controller ingress class and annotations
- production replicas, resources, HPAs, PDBs, and NetworkPolicies
- AI and connector configuration placeholders

The workflow overrides image repositories, image tag, namespace, ingress host, frontend API base URL, and backend Secret name at deploy time.

## Secrets

Do not commit secrets to the repository.

The Helm chart expects an existing Kubernetes Secret, defaulting to:

```text
accessiq-backend-runtime
```

Required keys:

```text
DATABASE_URL
JWT_SECRET
OPENAI_API_KEY
ANTHROPIC_API_KEY
```

For development AWS demos, empty AI provider keys are acceptable when `LLM_PROVIDER=mock`.

Terraform creates Secrets Manager placeholders named like:

```text
accessiq-dev/jwt
accessiq-dev/database_password
accessiq-dev/openai_api_key
accessiq-dev/anthropic_api_key
accessiq-dev/connector_credentials
```

RDS also creates an AWS-managed master user secret. A production workflow should use an external secret operator, sealed secret workflow, or controlled manual sync to create the Kubernetes Secret from AWS Secrets Manager.

Manual Kubernetes Secret example:

```bash
kubectl -n accessiq create secret generic accessiq-backend-runtime \
  --from-literal=DATABASE_URL='postgresql+psycopg://accessiq:<password>@<rds-endpoint>:5432/accessiq' \
  --from-literal=JWT_SECRET='<strong-random-secret>' \
  --from-literal=OPENAI_API_KEY='' \
  --from-literal=ANTHROPIC_API_KEY=''
```

## Manual Deployment

After Terraform has created infrastructure and images have been pushed to ECR, configure kubeconfig:

```bash
aws eks update-kubeconfig \
  --region us-east-1 \
  --name accessiq-dev
```

Deploy with Helm:

```bash
helm upgrade --install accessiq helm/accessiq \
  --namespace accessiq \
  --create-namespace \
  -f helm/accessiq/values-aws.yaml \
  --set namespace.name=accessiq \
  --set-string backend.image.repository=<account-id>.dkr.ecr.us-east-1.amazonaws.com/accessiq-dev-backend \
  --set-string backend.image.tag=<git-sha> \
  --set-string frontend.image.repository=<account-id>.dkr.ecr.us-east-1.amazonaws.com/accessiq-dev-frontend \
  --set-string frontend.image.tag=<git-sha> \
  --set-string ingress.host=<dns-name> \
  --set-string frontend.apiBaseUrl=https://<dns-name> \
  --set-string backend.config.corsAllowedOrigins=https://<dns-name> \
  --set-string backend.secrets.existingSecret=accessiq-backend-runtime \
  --wait \
  --timeout 10m
```

Verify rollout:

```bash
kubectl -n accessiq rollout status deployment \
  -l app.kubernetes.io/instance=accessiq,app.kubernetes.io/component=backend

kubectl -n accessiq rollout status deployment \
  -l app.kubernetes.io/instance=accessiq,app.kubernetes.io/component=frontend

kubectl -n accessiq get pods,services,ingress
```

## Smoke Tests

The smoke-test script lives at:

```text
scripts/aws-smoke-test.sh
```

It verifies:

- `/health`
- frontend root `/`
- `/openapi.json`
- `POST /login`
- authenticated `GET /ai/providers`

Run it manually:

```bash
ACCESSIQ_BASE_URL=https://<dns-name> bash scripts/aws-smoke-test.sh
```

Optional variables:

```bash
ACCESSIQ_SMOKE_EMAIL=alice@example.com
ACCESSIQ_SMOKE_PASSWORD='Password123!'
```

## Rollback

View release history:

```bash
helm history accessiq --namespace accessiq
```

Roll back to the previous release:

```bash
helm rollback accessiq --namespace accessiq
```

Roll back to a specific revision:

```bash
helm rollback accessiq <revision> --namespace accessiq
```

Because image tags are immutable, rollback restores the image tag recorded in the Helm revision.

## Troubleshooting

- `AccessDenied` during OIDC: verify the role trust policy `aud` and `sub` conditions match the repository and GitHub environment.
- `ECR repository not found`: run Terraform for the selected environment or verify the workflow `environment` input.
- `kubectl` unauthorized: grant the IAM role EKS access and Kubernetes RBAC in the target cluster.
- `Secret not found`: create the backend runtime Secret in the selected namespace before deployment.
- `ImagePullBackOff`: verify the node role can read ECR and the workflow pushed the expected immutable tag.
- ALB not created: verify AWS Load Balancer Controller is installed and its IRSA role is configured.
- Health checks failing: verify `DATABASE_URL`, RDS security group ingress, NetworkPolicy egress, and backend logs.
- Smoke login fails: confirm seed users exist and the smoke credentials match the target database.
