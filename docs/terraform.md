# Terraform Workflow

AccessIQ Terraform lives under `infrastructure/terraform` and prepares AWS infrastructure for a future EKS deployment. Terraform manages infrastructure only; it does not build images, deploy Helm releases, or populate application secrets.

## Module Structure

```text
infrastructure/terraform/
  modules/
    network/   VPC, public/private subnets, route tables, NAT
    iam/       EKS, node, Load Balancer Controller, and future CI roles
    eks/       EKS cluster, managed node group, OIDC provider
    rds/       Private PostgreSQL RDS instance
    ecr/       Backend and frontend ECR repositories
    secrets/   Secrets Manager secret shells
  environments/
    dev/       Lower-cost development defaults
    prod/      Production-oriented HA defaults
```

Each environment is a separate Terraform root module. Keep state, plans, and variable files isolated per environment.

## Remote Backend

Both `dev` and `prod` include an example partial S3 backend:

```hcl
terraform {
  backend "s3" {}
}
```

The active backend file is not committed by default so validation and planning can run before the S3 backend exists. During bootstrap, copy `backend.tf.example` to `backend.tf` and copy `backend.example.hcl` to `backend.hcl`. Both active files are ignored by Git.

Backend details are supplied at initialization time through the uncommitted `backend.hcl` file.

AccessIQ uses separate state keys:

```text
accessiq/dev/terraform.tfstate
accessiq/prod/terraform.tfstate
```

The backend examples enable S3 native state locking:

```hcl
use_lockfile = true
```

This avoids committing a DynamoDB lock-table dependency for this milestone. If a team later requires DynamoDB locking for compatibility with older Terraform versions, document that change and update the backend examples consistently.

## Bootstrap

Terraform cannot create or manage its own backend until the backend exists. Bootstrap the backend once per AWS account before normal environment initialization.

Recommended backend resources:

- A globally unique S3 bucket dedicated to Terraform state.
- Bucket versioning enabled.
- Server-side encryption enabled.
- Public access blocked.
- Least-privilege IAM access for human operators and future CI roles.

Example AWS CLI bootstrap commands:

```bash
aws s3api create-bucket \
  --bucket <unique-terraform-state-bucket> \
  --region us-east-1

aws s3api put-bucket-versioning \
  --bucket <unique-terraform-state-bucket> \
  --versioning-configuration Status=Enabled

aws s3api put-public-access-block \
  --bucket <unique-terraform-state-bucket> \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws s3api put-bucket-encryption \
  --bucket <unique-terraform-state-bucket> \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

Do not store AWS credentials, access keys, or secret values in backend files.

## Environment Initialization

From an environment directory:

```bash
cd infrastructure/terraform/environments/dev
cp backend.tf.example backend.tf
cp backend.example.hcl backend.hcl
```

Edit `backend.hcl` and set the real bucket name. `backend.tf` and `backend.hcl` are intentionally ignored by Git.

Initialize with the backend:

```bash
terraform init -backend-config=backend.hcl
```

Repeat the same pattern for `prod`, using the `prod` environment directory and `accessiq/prod/terraform.tfstate` state key from its example file.

## Pre-Bootstrap Validation

If the S3 backend has not been created yet, static validation can still run without configuring a backend:

```bash
terraform init
terraform validate
```

Use this only before backend bootstrap. Collaborative planning and apply workflows should use the configured S3 backend.

## Planning

Run formatting from the repository root:

```bash
terraform fmt -recursive infrastructure/terraform
```

Run validation and planning from the target environment:

```bash
cd infrastructure/terraform/environments/dev
terraform init -backend-config=backend.hcl
terraform validate
terraform plan
```

Plans read AWS account state and may fail if credentials, region, or permissions are missing. `terraform plan` does not create AWS resources.

## Applying

Only apply after reviewing cost, target account, target region, backend configuration, and planned resources:

```bash
terraform apply
```

Do not run apply from CI until the repository has explicit approval gates, protected environments, and a reviewed deployment workflow.

## Destroying

Destroy from the same environment directory and backend used for apply:

```bash
terraform destroy
```

Before destroying production, review RDS deletion protection, final snapshots, ECR image retention, Secrets Manager recovery windows, Kubernetes load balancers, and persistent volumes.

## State Management

The repository intentionally does not commit:

- `.terraform/`
- local `terraform.tfstate` files
- local `terraform.tfvars` files
- local `backend.tf` files
- local `backend.hcl` files
- provider plugin caches
- crash logs
- override files

Provider lockfiles, such as `.terraform.lock.hcl`, are committed so each environment resolves the same provider versions.

## Version Pinning

The environment roots pin:

- Terraform: `>= 1.10.0, < 2.0.0`
- AWS provider: `~> 5.100`
- TLS provider: `~> 4.0`

There are no Terraform Helm or Kubernetes providers in this milestone. Helm remains managed through the existing chart under `helm/accessiq`.

## Future GitHub Actions

Future CI should run:

```bash
terraform fmt -recursive -check infrastructure/terraform
terraform init
terraform validate
terraform plan
```

For pull requests, CI should publish plan output for review but must not run `terraform apply`.

Future deployment workflows should use GitHub Actions OIDC to assume a narrowly scoped AWS IAM role. Store no long-lived AWS access keys in the repository.
