variable "aws_region" {
  description = "AWS region for the production environment."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used in resource naming."
  type        = string
  default     = "accessiq"
}

variable "environment" {
  description = "Environment name."
  type        = string
  default     = "prod"
}

variable "cluster_version" {
  description = "EKS Kubernetes version."
  type        = string
  default     = "1.29"
}

variable "github_repositories" {
  description = "Repositories allowed to assume the future GitHub Actions role, formatted as owner/repo."
  type        = list(string)
  default     = []
}

variable "github_oidc_thumbprints" {
  description = "GitHub Actions OIDC thumbprints, required only when enabling GitHub OIDC provider creation."
  type        = list(string)
  default     = []
}

variable "enable_github_actions_oidc" {
  description = "Enable future GitHub Actions OIDC provider and role creation."
  type        = bool
  default     = false
}
