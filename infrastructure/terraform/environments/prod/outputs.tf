output "cluster_name" {
  description = "EKS cluster name."
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS cluster API endpoint."
  value       = module.eks.cluster_endpoint
}

output "vpc_id" {
  description = "VPC ID."
  value       = module.network.vpc_id
}

output "public_subnet_ids" {
  description = "Public subnet IDs."
  value       = module.network.public_subnet_ids
}

output "private_subnet_ids" {
  description = "Private subnet IDs."
  value       = module.network.private_subnet_ids
}

output "rds_endpoint" {
  description = "RDS endpoint."
  value       = module.rds.db_endpoint
}

output "rds_master_user_secret_arn" {
  description = "AWS-managed RDS master user secret ARN."
  value       = module.rds.master_user_secret_arn
}

output "ecr_repository_urls" {
  description = "ECR repository URLs."
  value       = module.ecr.repository_urls
}

output "secret_arns" {
  description = "Secrets Manager secret ARNs."
  value       = module.secrets.secret_arns
}

output "load_balancer_controller_role_arn" {
  description = "AWS Load Balancer Controller IAM role ARN."
  value       = module.iam_workload.load_balancer_controller_role_arn
}

output "github_actions_role_arn" {
  description = "Future GitHub Actions role ARN, when enabled."
  value       = module.iam_workload.github_actions_role_arn
}
