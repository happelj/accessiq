locals {
  oidc_condition_key = var.oidc_provider_url == null ? null : replace(var.oidc_provider_url, "https://", "")
  github_provider_arn = (
    var.create_github_actions_oidc_provider
    ? try(aws_iam_openid_connect_provider.github[0].arn, null)
    : var.github_oidc_provider_arn
  )
}

data "aws_iam_policy_document" "eks_cluster_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eks_cluster" {
  count = var.create_eks_cluster_role ? 1 : 0

  name               = "${var.name}-eks-cluster"
  assume_role_policy = data.aws_iam_policy_document.eks_cluster_assume.json

  tags = merge(var.tags, {
    Name = "${var.name}-eks-cluster"
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster" {
  for_each = var.create_eks_cluster_role ? toset([
    "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  ]) : toset([])

  role       = aws_iam_role.eks_cluster[0].name
  policy_arn = each.value
}

data "aws_iam_policy_document" "eks_node_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eks_node" {
  count = var.create_eks_node_role ? 1 : 0

  name               = "${var.name}-eks-node"
  assume_role_policy = data.aws_iam_policy_document.eks_node_assume.json

  tags = merge(var.tags, {
    Name = "${var.name}-eks-node"
  })
}

resource "aws_iam_role_policy_attachment" "eks_node" {
  for_each = var.create_eks_node_role ? toset([
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  ]) : toset([])

  role       = aws_iam_role.eks_node[0].name
  policy_arn = each.value
}

data "aws_iam_policy_document" "load_balancer_controller_assume" {
  count = var.create_load_balancer_controller_role ? 1 : 0

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_condition_key}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_condition_key}:sub"
      values = [
        "system:serviceaccount:${var.load_balancer_controller_namespace}:${var.load_balancer_controller_service_account}"
      ]
    }
  }
}

resource "aws_iam_role" "load_balancer_controller" {
  count = var.create_load_balancer_controller_role ? 1 : 0

  name               = "${var.name}-aws-load-balancer-controller"
  assume_role_policy = data.aws_iam_policy_document.load_balancer_controller_assume[0].json

  tags = merge(var.tags, {
    Name = "${var.name}-aws-load-balancer-controller"
  })
}

data "aws_iam_policy_document" "load_balancer_controller" {
  count = var.create_load_balancer_controller_role ? 1 : 0

  statement {
    sid = "LoadBalancerControllerCore"
    actions = [
      "acm:DescribeCertificate",
      "acm:ListCertificates",
      "acm:GetCertificate",
      "ec2:AuthorizeSecurityGroupIngress",
      "ec2:CreateSecurityGroup",
      "ec2:CreateTags",
      "ec2:DeleteSecurityGroup",
      "ec2:DeleteTags",
      "ec2:DescribeAccountAttributes",
      "ec2:DescribeAddresses",
      "ec2:DescribeAvailabilityZones",
      "ec2:DescribeCoipPools",
      "ec2:DescribeInstances",
      "ec2:DescribeInternetGateways",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeSubnets",
      "ec2:DescribeTags",
      "ec2:DescribeVpcs",
      "ec2:RevokeSecurityGroupIngress",
      "elasticloadbalancing:AddListenerCertificates",
      "elasticloadbalancing:AddTags",
      "elasticloadbalancing:CreateListener",
      "elasticloadbalancing:CreateLoadBalancer",
      "elasticloadbalancing:CreateRule",
      "elasticloadbalancing:CreateTargetGroup",
      "elasticloadbalancing:DeleteListener",
      "elasticloadbalancing:DeleteLoadBalancer",
      "elasticloadbalancing:DeleteRule",
      "elasticloadbalancing:DeleteTargetGroup",
      "elasticloadbalancing:DeregisterTargets",
      "elasticloadbalancing:DescribeListenerCertificates",
      "elasticloadbalancing:DescribeListeners",
      "elasticloadbalancing:DescribeLoadBalancers",
      "elasticloadbalancing:DescribeLoadBalancerAttributes",
      "elasticloadbalancing:DescribeRules",
      "elasticloadbalancing:DescribeSSLPolicies",
      "elasticloadbalancing:DescribeTags",
      "elasticloadbalancing:DescribeTargetGroups",
      "elasticloadbalancing:DescribeTargetGroupAttributes",
      "elasticloadbalancing:DescribeTargetHealth",
      "elasticloadbalancing:ModifyListener",
      "elasticloadbalancing:ModifyLoadBalancerAttributes",
      "elasticloadbalancing:ModifyRule",
      "elasticloadbalancing:ModifyTargetGroup",
      "elasticloadbalancing:ModifyTargetGroupAttributes",
      "elasticloadbalancing:RegisterTargets",
      "elasticloadbalancing:RemoveListenerCertificates",
      "elasticloadbalancing:RemoveTags",
      "elasticloadbalancing:SetIpAddressType",
      "elasticloadbalancing:SetSecurityGroups",
      "elasticloadbalancing:SetSubnets",
      "elasticloadbalancing:SetWebAcl",
      "iam:CreateServiceLinkedRole",
      "shield:CreateProtection",
      "shield:DeleteProtection",
      "shield:DescribeProtection",
      "shield:GetSubscriptionState",
      "waf-regional:AssociateWebACL",
      "waf-regional:DisassociateWebACL",
      "waf-regional:GetWebACL",
      "waf-regional:GetWebACLForResource",
      "wafv2:AssociateWebACL",
      "wafv2:DisassociateWebACL",
      "wafv2:GetWebACL",
      "wafv2:GetWebACLForResource"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "load_balancer_controller" {
  count = var.create_load_balancer_controller_role ? 1 : 0

  name        = "${var.name}-aws-load-balancer-controller"
  description = "IAM policy for the AWS Load Balancer Controller."
  policy      = data.aws_iam_policy_document.load_balancer_controller[0].json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "load_balancer_controller" {
  count = var.create_load_balancer_controller_role ? 1 : 0

  role       = aws_iam_role.load_balancer_controller[0].name
  policy_arn = aws_iam_policy.load_balancer_controller[0].arn
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_actions_oidc_provider ? 1 : 0

  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = var.github_oidc_thumbprints

  tags = merge(var.tags, {
    Name = "${var.name}-github-actions-oidc"
  })
}

data "aws_iam_policy_document" "github_actions_assume" {
  count = var.create_github_actions_role && (var.create_github_actions_oidc_provider || var.github_oidc_provider_arn != null) && length(var.github_repositories) > 0 ? 1 : 0

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.github_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [for repository in var.github_repositories : "repo:${repository}:*"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  count = var.create_github_actions_role && (var.create_github_actions_oidc_provider || var.github_oidc_provider_arn != null) && length(var.github_repositories) > 0 ? 1 : 0

  name               = "${var.name}-github-actions"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume[0].json

  tags = merge(var.tags, {
    Name = "${var.name}-github-actions"
  })
}

data "aws_iam_policy_document" "github_actions" {
  count = var.create_github_actions_role && length(var.ecr_repository_arns) > 0 && var.eks_cluster_arn != null ? 1 : 0

  statement {
    sid       = "EcrAuthorization"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "EcrImagePush"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart"
    ]
    resources = var.ecr_repository_arns
  }

  statement {
    sid       = "EksDescribeCluster"
    actions   = ["eks:DescribeCluster"]
    resources = [var.eks_cluster_arn]
  }
}

resource "aws_iam_policy" "github_actions" {
  count = var.create_github_actions_role && length(var.ecr_repository_arns) > 0 && var.eks_cluster_arn != null ? 1 : 0

  name        = "${var.name}-github-actions"
  description = "Future CI/CD policy for publishing AccessIQ images and reading EKS cluster metadata."
  policy      = data.aws_iam_policy_document.github_actions[0].json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "github_actions" {
  count = length(aws_iam_role.github_actions) > 0 && length(aws_iam_policy.github_actions) > 0 ? 1 : 0

  role       = aws_iam_role.github_actions[0].name
  policy_arn = aws_iam_policy.github_actions[0].arn
}
