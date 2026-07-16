variable "name" {
  description = "Name prefix for Secrets Manager resources."
  type        = string
}

variable "kms_key_id" {
  description = "Optional KMS key ID for secret encryption. Defaults to the AWS managed key."
  type        = string
  default     = null
}

variable "secrets" {
  description = "Secrets to create. Values are intentionally not populated by default."
  type = map(object({
    name                    = optional(string)
    description             = string
    recovery_window_in_days = optional(number, 7)
  }))
}

variable "tags" {
  description = "Tags applied to all supported resources."
  type        = map(string)
  default     = {}
}
