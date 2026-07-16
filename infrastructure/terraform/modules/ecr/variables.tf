variable "name" {
  description = "Name prefix for ECR repositories."
  type        = string
}

variable "repositories" {
  description = "Logical repository names to create."
  type        = set(string)
  default     = ["backend", "frontend"]
}

variable "image_tag_mutability" {
  description = "ECR tag mutability setting."
  type        = string
  default     = "IMMUTABLE"
}

variable "scan_on_push" {
  description = "Enable image scan on push."
  type        = bool
  default     = true
}

variable "force_delete" {
  description = "Allow Terraform to delete repositories that contain images."
  type        = bool
  default     = false
}

variable "lifecycle_max_images" {
  description = "Maximum number of tagged images to retain."
  type        = number
  default     = 25
}

variable "tags" {
  description = "Tags applied to all supported resources."
  type        = map(string)
  default     = {}
}
