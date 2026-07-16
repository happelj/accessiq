variable "name" {
  description = "Name prefix for IAM resources."
  type        = string
}

variable "create_eks_cluster_role" {
  description = "Create the IAM role used by the EKS control plane."
  type        = bool
  default     = true
}

variable "create_eks_node_role" {
  description = "Create the IAM role used by EKS managed node groups."
  type        = bool
  default     = true
}

variable "create_load_balancer_controller_role" {
  description = "Create the IRSA role and policy for the AWS Load Balancer Controller."
  type        = bool
  default     = false
}

variable "oidc_provider_arn" {
  description = "EKS OIDC provider ARN used for IRSA roles."
  type        = string
  default     = null
}

variable "oidc_provider_url" {
  description = "EKS OIDC issuer URL used for IRSA trust conditions."
  type        = string
  default     = null
}

variable "load_balancer_controller_namespace" {
  description = "Kubernetes namespace for the AWS Load Balancer Controller service account."
  type        = string
  default     = "kube-system"
}

variable "load_balancer_controller_service_account" {
  description = "Kubernetes service account name for the AWS Load Balancer Controller."
  type        = string
  default     = "aws-load-balancer-controller"
}

variable "create_github_actions_oidc_provider" {
  description = "Create a GitHub Actions OIDC provider for future CI/CD use."
  type        = bool
  default     = false
}

variable "create_github_actions_role" {
  description = "Create a constrained GitHub Actions role for future image publishing and cluster access."
  type        = bool
  default     = false
}

variable "github_oidc_provider_arn" {
  description = "Existing GitHub Actions OIDC provider ARN. Used when create_github_actions_oidc_provider is false."
  type        = string
  default     = null
}

variable "github_oidc_thumbprints" {
  description = "Thumbprints for the GitHub Actions OIDC provider when this module creates it."
  type        = list(string)
  default     = []
}

variable "github_repositories" {
  description = "GitHub repositories allowed to assume the future CI/CD role, formatted as owner/repo."
  type        = list(string)
  default     = []
}

variable "ecr_repository_arns" {
  description = "ECR repository ARNs the future CI/CD role may push to."
  type        = list(string)
  default     = []
}

variable "eks_cluster_arn" {
  description = "EKS cluster ARN the future CI/CD role may describe."
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags applied to all supported resources."
  type        = map(string)
  default     = {}
}
