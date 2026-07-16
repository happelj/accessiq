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

Run from an environment directory:

```bash
cd infrastructure/terraform/environments/dev
terraform init
terraform fmt -recursive ../..
terraform validate
terraform plan
```

Do not run `terraform apply` until AWS account, region, cost, and naming choices have been reviewed.

## Notes

- This milestone creates AWS infrastructure only.
- It does not deploy AccessIQ to EKS.
- It does not push container images.
- It does not configure GitHub Actions deployment.
- Secrets Manager resources are created without secret values; populate them out-of-band before deployment.
