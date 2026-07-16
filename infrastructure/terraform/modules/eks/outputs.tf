output "cluster_name" {
  description = "EKS cluster name."
  value       = aws_eks_cluster.this.name
}

output "cluster_arn" {
  description = "EKS cluster ARN."
  value       = aws_eks_cluster.this.arn
}

output "cluster_endpoint" {
  description = "EKS cluster API endpoint."
  value       = aws_eks_cluster.this.endpoint
}

output "cluster_certificate_authority_data" {
  description = "Base64-encoded EKS cluster certificate authority data."
  value       = aws_eks_cluster.this.certificate_authority[0].data
  sensitive   = true
}

output "cluster_security_group_id" {
  description = "EKS cluster security group ID."
  value       = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
}

output "additional_cluster_security_group_id" {
  description = "Additional security group created by this module."
  value       = aws_security_group.cluster.id
}

output "node_group_name" {
  description = "Default managed node group name."
  value       = aws_eks_node_group.default.node_group_name
}

output "oidc_provider_arn" {
  description = "EKS OIDC provider ARN."
  value       = aws_iam_openid_connect_provider.this.arn
}

output "oidc_provider_url" {
  description = "EKS OIDC provider URL."
  value       = aws_iam_openid_connect_provider.this.url
}
