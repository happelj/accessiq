locals {
  name = "${var.project_name}-${var.environment}"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  placeholder_secrets = {
    jwt = {
      description = "AccessIQ JWT signing secret. Populate with a strong random value before deployment."
    }
    database_password = {
      description = "Placeholder for database password workflows. RDS master password is AWS-managed by default."
    }
    openai_api_key = {
      description = "Optional OpenAI API key for AI explanations."
    }
    anthropic_api_key = {
      description = "Optional Anthropic API key for AI explanations."
    }
    connector_credentials = {
      description = "Placeholder JSON secret for future connector credentials."
    }
  }
}

module "network" {
  source = "../../modules/network"

  name                 = local.name
  vpc_cidr             = "10.40.0.0/16"
  az_count             = 2
  public_subnet_cidrs  = ["10.40.0.0/24", "10.40.1.0/24"]
  private_subnet_cidrs = ["10.40.10.0/24", "10.40.11.0/24"]
  enable_nat_gateway   = true
  single_nat_gateway   = true
  tags                 = local.common_tags
}

module "iam" {
  source = "../../modules/iam"

  name = local.name
  tags = local.common_tags
}

module "eks" {
  source = "../../modules/eks"

  name                         = local.name
  cluster_version              = var.cluster_version
  vpc_id                       = module.network.vpc_id
  private_subnet_ids           = module.network.private_subnet_ids
  cluster_role_arn             = module.iam.eks_cluster_role_arn
  node_role_arn                = module.iam.eks_node_role_arn
  endpoint_private_access      = true
  endpoint_public_access       = true
  endpoint_public_access_cidrs = ["0.0.0.0/0"]
  node_instance_types          = ["t3.medium"]
  node_desired_size            = 2
  node_min_size                = 2
  node_max_size                = 4
  node_disk_size               = 30
  tags                         = local.common_tags

  depends_on = [module.iam]
}

module "iam_workload" {
  source = "../../modules/iam"

  name                                      = "${local.name}-workload"
  create_eks_cluster_role                   = false
  create_eks_node_role                      = false
  create_load_balancer_controller_role      = true
  oidc_provider_arn                         = module.eks.oidc_provider_arn
  oidc_provider_url                         = module.eks.oidc_provider_url
  create_github_actions_oidc_provider       = var.enable_github_actions_oidc
  create_github_actions_role                = var.enable_github_actions_oidc
  github_oidc_thumbprints                   = var.github_oidc_thumbprints
  github_repositories                       = var.github_repositories
  ecr_repository_arns                       = values(module.ecr.repository_arns)
  eks_cluster_arn                           = module.eks.cluster_arn
  tags                                      = local.common_tags
}

module "rds" {
  source = "../../modules/rds"

  name                       = local.name
  vpc_id                     = module.network.vpc_id
  private_subnet_ids         = module.network.private_subnet_ids
  allowed_security_group_ids = [module.eks.cluster_security_group_id]
  instance_class             = "db.t4g.micro"
  allocated_storage          = 20
  max_allocated_storage      = 100
  backup_retention_period    = 7
  multi_az                   = false
  deletion_protection        = false
  skip_final_snapshot        = true
  tags                       = local.common_tags
}

module "ecr" {
  source = "../../modules/ecr"

  name                 = local.name
  repositories         = ["backend", "frontend"]
  image_tag_mutability = "IMMUTABLE"
  scan_on_push         = true
  force_delete         = false
  lifecycle_max_images = 15
  tags                 = local.common_tags
}

module "secrets" {
  source = "../../modules/secrets"

  name    = local.name
  secrets = local.placeholder_secrets
  tags    = local.common_tags
}
