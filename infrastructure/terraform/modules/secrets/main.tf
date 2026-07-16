resource "aws_secretsmanager_secret" "this" {
  for_each = var.secrets

  name                    = coalesce(each.value.name, "${var.name}/${each.key}")
  description             = each.value.description
  kms_key_id              = var.kms_key_id
  recovery_window_in_days = each.value.recovery_window_in_days

  tags = merge(var.tags, {
    Name = coalesce(each.value.name, "${var.name}/${each.key}")
  })
}
