output "db_instance_identifier" {
  description = "RDS instance identifier."
  value       = aws_db_instance.this.identifier
}

output "db_endpoint" {
  description = "RDS endpoint with port."
  value       = aws_db_instance.this.endpoint
}

output "db_address" {
  description = "RDS hostname."
  value       = aws_db_instance.this.address
}

output "db_port" {
  description = "RDS port."
  value       = aws_db_instance.this.port
}

output "db_security_group_id" {
  description = "RDS security group ID."
  value       = aws_security_group.this.id
}

output "master_user_secret_arn" {
  description = "AWS-managed master user secret ARN."
  value       = try(aws_db_instance.this.master_user_secret[0].secret_arn, null)
}
