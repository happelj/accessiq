variable "name" {
  description = "EKS cluster name."
  type        = string
}

variable "cluster_version" {
  description = "EKS Kubernetes version."
  type        = string
  default     = "1.29"
}

variable "vpc_id" {
  description = "VPC ID for the cluster."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for control plane networking and managed nodes."
  type        = list(string)
}

variable "cluster_role_arn" {
  description = "IAM role ARN used by the EKS control plane."
  type        = string
}

variable "node_role_arn" {
  description = "IAM role ARN used by EKS managed nodes."
  type        = string
}

variable "endpoint_private_access" {
  description = "Enable private access to the EKS API endpoint."
  type        = bool
  default     = true
}

variable "endpoint_public_access" {
  description = "Enable public access to the EKS API endpoint."
  type        = bool
  default     = true
}

variable "endpoint_public_access_cidrs" {
  description = "CIDR blocks allowed to reach the public EKS API endpoint."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "enabled_cluster_log_types" {
  description = "EKS control plane log types to enable."
  type        = list(string)
  default     = ["api", "audit", "authenticator"]
}

variable "node_instance_types" {
  description = "Instance types for the default managed node group."
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_capacity_type" {
  description = "Capacity type for managed nodes."
  type        = string
  default     = "ON_DEMAND"
}

variable "node_disk_size" {
  description = "Managed node disk size in GiB."
  type        = number
  default     = 30
}

variable "node_desired_size" {
  description = "Desired number of managed nodes."
  type        = number
  default     = 2
}

variable "node_min_size" {
  description = "Minimum number of managed nodes."
  type        = number
  default     = 2
}

variable "node_max_size" {
  description = "Maximum number of managed nodes."
  type        = number
  default     = 4
}

variable "tags" {
  description = "Tags applied to all supported resources."
  type        = map(string)
  default     = {}
}
