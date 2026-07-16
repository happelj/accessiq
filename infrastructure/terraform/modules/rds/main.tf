resource "aws_security_group" "this" {
  name        = "${var.name}-postgresql"
  description = "PostgreSQL access for AccessIQ."
  vpc_id      = var.vpc_id

  egress {
    description = "Allow database egress"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.name}-postgresql"
  })
}

resource "aws_security_group_rule" "postgresql_ingress" {
  count = length(var.allowed_security_group_ids)

  type                     = "ingress"
  description              = "Allow PostgreSQL from ${var.allowed_security_group_ids[count.index]}"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.this.id
  source_security_group_id = var.allowed_security_group_ids[count.index]
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-postgresql"
  subnet_ids = var.private_subnet_ids

  tags = merge(var.tags, {
    Name = "${var.name}-postgresql"
  })
}

resource "aws_db_parameter_group" "this" {
  name   = "${var.name}-postgresql"
  family = var.family

  dynamic "parameter" {
    for_each = var.parameters

    content {
      name  = parameter.value.name
      value = parameter.value.value
    }
  }

  tags = merge(var.tags, {
    Name = "${var.name}-postgresql"
  })
}

resource "aws_db_instance" "this" {
  identifier = "${var.name}-postgresql"

  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  db_name  = var.database_name
  username = var.master_username

  manage_master_user_password = true

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.this.id]
  parameter_group_name   = aws_db_parameter_group.this.name
  publicly_accessible    = false

  backup_retention_period   = var.backup_retention_period
  copy_tags_to_snapshot     = true
  deletion_protection       = var.deletion_protection
  multi_az                  = var.multi_az
  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${var.name}-postgresql-final"

  auto_minor_version_upgrade = true
  apply_immediately          = false

  tags = merge(var.tags, {
    Name = "${var.name}-postgresql"
  })
}
