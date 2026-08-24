# AWS IAM FOR K3S WORKERS
# Tạo IAM Role cho Worker Nodes
data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "worker_role" {
  name               = "mlops-worker-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
}

# Policy cho phép Worker Node đọc/ghi vào S3 Bucket của dự án
data "aws_iam_policy_document" "worker_s3_policy_doc" {
  statement {
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:ListBucket",
      "s3:DeleteObject",
      "s3:ListBucketMultipartUploads",
      "s3:ListMultipartUploadParts",
      "s3:AbortMultipartUpload",
      "s3:GetBucketLocation"
    ]
    resources = [
      var.artifacts_bucket_arn,
      "${var.artifacts_bucket_arn}/*"
    ]
  }
}

resource "aws_iam_policy" "worker_s3_policy" {
  name        = "mlops-worker-s3-policy"
  description = "Allow K3s worker nodes to read/write artifacts in project bucket"
  policy      = data.aws_iam_policy_document.worker_s3_policy_doc.json
}

# Gắn policy đọc/ghi S3 vào Worker Role
resource "aws_iam_role_policy_attachment" "worker_s3_attach" {
  role       = aws_iam_role.worker_role.name
  policy_arn = aws_iam_policy.worker_s3_policy.arn
}

# Tạo Policy cho phép Worker Node đọc Secrets Manager
data "aws_iam_policy_document" "secrets_read_policy" {
  statement {
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "worker_secrets_policy" {
  name        = "mlops-worker-secrets-policy"
  description = "Allow K3s worker nodes to read secrets from AWS Secrets Manager"
  policy      = data.aws_iam_policy_document.secrets_read_policy.json
}

# Gắn quyền đọc secrets cho Worker Nodes
resource "aws_iam_role_policy_attachment" "worker_secrets_attach" {
  role       = aws_iam_role.worker_role.name
  policy_arn = aws_iam_policy.worker_secrets_policy.arn
}

# Gắn quyền cho EBS CSI Driver để tự động cấp phát ổ cứng AWS EBS
resource "aws_iam_role_policy_attachment" "worker_ebs_csi_attach" {
  role       = aws_iam_role.worker_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

# Tạo Instance Profile để gắn vào EC2
resource "aws_iam_instance_profile" "worker_profile" {
  name = "mlops-worker-profile"
  role = aws_iam_role.worker_role.name
}

# Karpenter IAM Role and Policies
data "aws_caller_identity" "current" {}

resource "aws_iam_role" "karpenter_node_role" {
  count              = var.enable_karpenter ? 1 : 0
  name               = "mlops-karpenter-node-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json

  tags = {
    "karpenter.sh/discovery" = var.karpenter_cluster_name
  }
}

resource "aws_iam_instance_profile" "karpenter_node_profile" {
  count = var.enable_karpenter ? 1 : 0
  name  = "mlops-karpenter-node-profile"
  role  = aws_iam_role.karpenter_node_role[0].name

  tags = {
    "karpenter.sh/discovery" = var.karpenter_cluster_name
  }
}

resource "aws_iam_role_policy_attachment" "karpenter_node_s3_attach" {
  count      = var.enable_karpenter ? 1 : 0
  role       = aws_iam_role.karpenter_node_role[0].name
  policy_arn = aws_iam_policy.worker_s3_policy.arn
}

data "aws_iam_policy_document" "karpenter_node_token_secret_policy_doc" {
  count = var.enable_karpenter ? 1 : 0

  statement {
    sid    = "ReadK3sAgentToken"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]
    resources = [var.karpenter_k3s_token_secret_arn]
  }
}

resource "aws_iam_policy" "karpenter_node_token_secret_policy" {
  count       = var.enable_karpenter ? 1 : 0
  name        = "mlops-karpenter-node-token-secret-policy"
  description = "Allow Karpenter nodes to read only the K3s agent join token"
  policy      = data.aws_iam_policy_document.karpenter_node_token_secret_policy_doc[0].json
}

resource "aws_iam_role_policy_attachment" "karpenter_node_token_secret_attach" {
  count      = var.enable_karpenter ? 1 : 0
  role       = aws_iam_role.karpenter_node_role[0].name
  policy_arn = aws_iam_policy.karpenter_node_token_secret_policy[0].arn
}

resource "aws_iam_role_policy_attachment" "karpenter_node_ebs_csi_attach" {
  count      = var.enable_karpenter ? 1 : 0
  role       = aws_iam_role.karpenter_node_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

data "aws_iam_policy_document" "karpenter_node_training_tag_policy_doc" {
  count = var.enable_karpenter ? 1 : 0

  statement {
    sid     = "AllowTrainingNodeNameTag"
    effect  = "Allow"
    actions = ["ec2:CreateTags"]
    resources = [
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:instance/*"
    ]

    condition {
      test     = "ForAllValues:StringEquals"
      variable = "aws:TagKeys"
      values   = ["Name"]
    }

    condition {
      test     = "StringLike"
      variable = "aws:ResourceTag/karpenter.sh/nodepool"
      values   = ["mlops-paas-training-*"]
    }
  }
}

resource "aws_iam_policy" "karpenter_node_training_tag_policy" {
  count       = var.enable_karpenter ? 1 : 0
  name        = "mlops-karpenter-node-training-tag-policy"
  description = "Allow Karpenter training nodes to set their EC2 Name tag from training job id"
  policy      = data.aws_iam_policy_document.karpenter_node_training_tag_policy_doc[0].json
}

resource "aws_iam_role_policy_attachment" "karpenter_node_training_tag_attach" {
  count      = var.enable_karpenter ? 1 : 0
  role       = aws_iam_role.karpenter_node_role[0].name
  policy_arn = aws_iam_policy.karpenter_node_training_tag_policy[0].arn
}

data "aws_iam_policy_document" "karpenter_controller_policy_doc" {
  count = var.enable_karpenter ? 1 : 0

  statement {
    sid    = "AllowScopedEC2InstanceActions"
    effect = "Allow"
    actions = [
      "ec2:CreateFleet",
      "ec2:RunInstances"
    ]
    resources = [
      "arn:aws:ec2:*::image/*",
      "arn:aws:ec2:*::snapshot/*",
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:launch-template/*",
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:security-group/*",
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:subnet/*",
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:fleet/*",
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:spot-instances-request/*",
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:instance/*",
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:volume/*",
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:network-interface/*"
    ]
  }

  statement {
    sid    = "AllowScopedEC2LaunchTemplateActions"
    effect = "Allow"
    actions = [
      "ec2:CreateLaunchTemplate",
      "ec2:CreateTags"
    ]
    resources = [
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:launch-template/*",
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:fleet/*",
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:spot-instances-request/*",
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:instance/*",
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:volume/*",
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:network-interface/*"
    ]
  }

  statement {
    sid    = "AllowScopedEC2Termination"
    effect = "Allow"
    actions = [
      "ec2:DeleteLaunchTemplate",
      "ec2:TerminateInstances"
    ]
    resources = [
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:launch-template/*",
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:instance/*"
    ]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/kubernetes.io/cluster/${var.karpenter_cluster_name}"
      values   = ["owned"]
    }

    condition {
      test     = "StringLike"
      variable = "aws:ResourceTag/karpenter.sh/nodepool"
      values   = ["*"]
    }
  }

  statement {
    sid    = "AllowEC2DescribeAndPricing"
    effect = "Allow"
    actions = [
      "ec2:DescribeAvailabilityZones",
      "ec2:DescribeImages",
      "ec2:DescribeInstanceTypeOfferings",
      "ec2:DescribeInstanceTypes",
      "ec2:DescribeInstances",
      "ec2:DescribeLaunchTemplates",
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeSpotPriceHistory",
      "ec2:DescribeSubnets",
      "iam:GetInstanceProfile",
      "iam:ListInstanceProfiles",
      "pricing:GetProducts",
      "ssm:GetParameter"
    ]
    resources = ["*"]
  }

  statement {
    sid     = "AllowPassingKarpenterNodeRole"
    effect  = "Allow"
    actions = ["iam:PassRole"]
    resources = [
      aws_iam_role.karpenter_node_role[0].arn
    ]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ec2.amazonaws.com"]
    }
  }

  statement {
    sid     = "AllowSpotServiceLinkedRole"
    effect  = "Allow"
    actions = ["iam:CreateServiceLinkedRole"]
    resources = [
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/aws-service-role/spot.amazonaws.com/AWSServiceRoleForEC2Spot"
    ]
    condition {
      test     = "StringLike"
      variable = "iam:AWSServiceName"
      values   = ["spot.amazonaws.com"]
    }
  }

  statement {
    sid    = "AllowInterruptionQueueRead"
    effect = "Allow"
    actions = [
      "sqs:DeleteMessage",
      "sqs:GetQueueUrl",
      "sqs:ReceiveMessage"
    ]
    resources = [
      aws_sqs_queue.karpenter_interruption_queue[0].arn
    ]
  }
}

resource "aws_iam_policy" "karpenter_controller_policy" {
  count       = var.enable_karpenter ? 1 : 0
  name        = "mlops-karpenter-controller-policy"
  description = "Allow Karpenter running on K3s workers to provision EC2 capacity"
  policy      = data.aws_iam_policy_document.karpenter_controller_policy_doc[0].json
}

resource "aws_iam_role_policy_attachment" "worker_karpenter_controller_attach" {
  count      = var.enable_karpenter ? 1 : 0
  role       = aws_iam_role.worker_role.name
  policy_arn = aws_iam_policy.karpenter_controller_policy[0].arn
}

resource "aws_sqs_queue" "karpenter_interruption_queue" {
  count                     = var.enable_karpenter ? 1 : 0
  name                      = var.karpenter_cluster_name
  message_retention_seconds = 300

  tags = {
    "karpenter.sh/discovery" = var.karpenter_cluster_name
  }
}

data "aws_iam_policy_document" "karpenter_interruption_queue_policy_doc" {
  count = var.enable_karpenter ? 1 : 0

  statement {
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.karpenter_interruption_queue[0].arn]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com", "sqs.amazonaws.com"]
    }
  }
}

resource "aws_sqs_queue_policy" "karpenter_interruption_queue_policy" {
  count     = var.enable_karpenter ? 1 : 0
  queue_url = aws_sqs_queue.karpenter_interruption_queue[0].id
  policy    = data.aws_iam_policy_document.karpenter_interruption_queue_policy_doc[0].json
}

locals {
  karpenter_interruption_events = var.enable_karpenter ? {
    rebalance = {
      description = "EC2 Instance Rebalance Recommendation for Karpenter"
      pattern = {
        source        = ["aws.ec2"]
        "detail-type" = ["EC2 Instance Rebalance Recommendation"]
      }
    }
    spot_interruption = {
      description = "EC2 Spot Instance Interruption Warning for Karpenter"
      pattern = {
        source        = ["aws.ec2"]
        "detail-type" = ["EC2 Spot Instance Interruption Warning"]
      }
    }
    instance_state_change = {
      description = "EC2 Instance State-change Notification for Karpenter"
      pattern = {
        source        = ["aws.ec2"]
        "detail-type" = ["EC2 Instance State-change Notification"]
      }
    }
    health_event = {
      description = "AWS Health Event for Karpenter"
      pattern = {
        source        = ["aws.health"]
        "detail-type" = ["AWS Health Event"]
      }
    }
  } : {}
}

resource "aws_cloudwatch_event_rule" "karpenter_interruption" {
  for_each      = local.karpenter_interruption_events
  name          = "mlops-karpenter-${each.key}"
  description   = each.value.description
  event_pattern = jsonencode(each.value.pattern)
}

resource "aws_cloudwatch_event_target" "karpenter_interruption_queue" {
  for_each  = local.karpenter_interruption_events
  rule      = aws_cloudwatch_event_rule.karpenter_interruption[each.key].name
  target_id = "KarpenterInterruptionQueue"
  arn       = aws_sqs_queue.karpenter_interruption_queue[0].arn
}


# GITHUB ACTIONS OIDC
# Tạo OIDC Provider cho GitHub
resource "aws_iam_openid_connect_provider" "github_actions" {
  count           = var.enable_github_oidc ? 1 : 0
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["1c58a3a8518e8759bf075b76b750d4f2df264fcd", "6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# Tạo IAM Role cho GitHub Actions
data "aws_iam_policy_document" "github_actions_assume_role" {
  count = var.enable_github_oidc ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions[0].arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      # Giới hạn chỉ Repository này mới được quyền dùng Role
      values = ["repo:Viet-Hoang-2005/MLOps-paas-system:*"]
    }
  }
}

resource "aws_iam_role" "github_actions_role" {
  count              = var.enable_github_oidc ? 1 : 0
  name               = "mlops-github-actions-role"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume_role[0].json
}

# Cấp quyền đọc Secret và S3 cho Role của GitHub Actions
data "aws_iam_policy_document" "github_actions_policy" {
  count = var.enable_github_oidc ? 1 : 0

  statement {
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue"
    ]
    resources = [
      var.github_actions_secrets_arn,
      var.mlflow_basic_auth_arn,
      var.github_secrets_arn,
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
      "s3:PutObject"
    ]
    resources = [
      var.artifacts_bucket_arn,
      "${var.artifacts_bucket_arn}/*"
    ]
  }
}

resource "aws_iam_role_policy" "github_actions_policy_attach" {
  count  = var.enable_github_oidc ? 1 : 0
  name   = "mlops-github-actions-policy"
  role   = aws_iam_role.github_actions_role[0].id
  policy = data.aws_iam_policy_document.github_actions_policy[0].json
}
