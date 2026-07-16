variable "name" {
  description = "Name prefix for RDS resources."
  type        = string
}

variable "vpc_id" {
  description = "VPC ID for the database security group."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for the DB subnet group."
  type        = list(string)
}

variable "allowed_security_group_ids" {
  description = "Security group IDs allowed to connect to PostgreSQL."
  type        = list(string)
  default     = []
}

variable "database_name" {
  description = "Initial PostgreSQL database name."
  type        = string
  default     = "accessiq"
}

variable "master_username" {
  description = "PostgreSQL master username."
  type        = string
  default     = "accessiq"
}

variable "engine_version" {
  description = "PostgreSQL engine version."
  type        = string
  default     = "16.6"
}

variable "family" {
  description = "PostgreSQL parameter group family."
  type        = string
  default     = "postgres16"
}

variable "instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage" {
  description = "Initial allocated storage in GiB."
  type        = number
  default     = 20
}

variable "max_allocated_storage" {
  description = "Maximum autoscaled storage in GiB."
  type        = number
  default     = 100
}

variable "backup_retention_period" {
  description = "Automated backup retention in days."
  type        = number
  default     = 7
}

variable "multi_az" {
  description = "Enable Multi-AZ RDS deployment."
  type        = bool
  default     = false
}

variable "deletion_protection" {
  description = "Enable RDS deletion protection."
  type        = bool
  default     = false
}

variable "skip_final_snapshot" {
  description = "Skip the final snapshot on deletion."
  type        = bool
  default     = true
}

variable "parameters" {
  description = "PostgreSQL parameter group settings."
  type = list(object({
    name  = string
    value = string
  }))
  default = []
}

variable "tags" {
  description = "Tags applied to all supported resources."
  type        = map(string)
  default     = {}
}
