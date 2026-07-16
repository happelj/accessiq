# AccessIQ Terraform

Terraform infrastructure for AWS lives under `infrastructure/terraform`.

## Layout

```text
modules/
  network/   VPC, public/private subnets, routing, NAT
  iam/       EKS, node, Load Balancer Controller, and future GitHub OIDC roles
  eks/       EKS cluster, managed node group, OIDC provider
  rds/       Private PostgreSQL RDS instance
  ecr/       Backend and frontend ECR repositories
  secrets/   Secrets Manager secret shells
environments/
  dev/       Lower-cost development defaults
  prod/      Production-oriented HA defaults
```

## Local Commands

Run formatting from the repository root:

```bash
terraform fmt -recursive infrastructure/terraform
```

Run static validation from an environment directory before the S3 backend exists:

```bash
cd infrastructure/terraform/environments/dev
terraform init
terraform validate
```

After backend bootstrap, copy the backend example and initialize the remote backend:

```bash
cp backend.tf.example backend.tf
cp backend.example.hcl backend.hcl
terraform init -backend-config=backend.hcl
terraform plan
```

Do not run `terraform apply` until AWS account, region, cost, and naming choices have been reviewed.

See `docs/terraform.md` for backend bootstrap, remote state, planning, applying, destroying, and future CI guidance.

## Notes

- This milestone creates AWS infrastructure only.
- It does not deploy AccessIQ to EKS.
- It does not push container images.
- It does not configure GitHub Actions deployment.
- Secrets Manager resources are created without secret values; populate them out-of-band before deployment.
