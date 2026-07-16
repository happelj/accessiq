output "eks_cluster_role_arn" {
  description = "EKS cluster role ARN."
  value       = try(aws_iam_role.eks_cluster[0].arn, null)
}

output "eks_node_role_arn" {
  description = "EKS managed node role ARN."
  value       = try(aws_iam_role.eks_node[0].arn, null)
}

output "load_balancer_controller_role_arn" {
  description = "AWS Load Balancer Controller IRSA role ARN."
  value       = try(aws_iam_role.load_balancer_controller[0].arn, null)
}

output "github_actions_role_arn" {
  description = "Future GitHub Actions OIDC role ARN."
  value       = try(aws_iam_role.github_actions[0].arn, null)
}

output "github_oidc_provider_arn" {
  description = "GitHub Actions OIDC provider ARN, when created."
  value       = try(aws_iam_openid_connect_provider.github[0].arn, null)
}
