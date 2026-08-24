locals {
  enable_k3s_compute_stack = (
    var.enable_k3s_compute &&
    var.enable_network &&
    var.enable_nat_gateway &&
    var.enable_artifact_storage &&
    var.enable_secrets_manager
  )
  enable_karpenter_stack = local.enable_k3s_compute_stack && var.enable_karpenter
  enable_alb_stack = (
    var.enable_alb &&
    local.enable_k3s_compute_stack &&
    var.enable_acm_certificate
  )
  enable_security_stack = var.enable_network && (
    var.enable_k3s_compute || var.enable_alb || var.enable_karpenter
  )
  enable_shared_iam = (
    var.enable_artifact_storage &&
    var.enable_secrets_manager &&
    (var.enable_k3s_compute || var.enable_github_oidc || var.enable_karpenter)
  )
}

module "network" {
  count                  = var.enable_network ? 1 : 0
  source                 = "./modules/network"
  enable_nat_gateway     = var.enable_nat_gateway
  enable_karpenter       = local.enable_karpenter_stack
  karpenter_cluster_name = var.karpenter_cluster_name
  vpc_cidr               = var.vpc_cidr
  public_subnet_1a_cidr  = var.public_subnet_1a_cidr
  public_subnet_1b_cidr  = var.public_subnet_1b_cidr
  private_subnet_1a_cidr = var.private_subnet_1a_cidr
}

module "security" {
  count                         = local.enable_security_stack ? 1 : 0
  source                        = "./modules/security"
  vpc_id                        = module.network[0].vpc_id
  enable_legacy_security_groups = local.enable_k3s_compute_stack || local.enable_alb_stack
  enable_karpenter              = local.enable_karpenter_stack
  karpenter_cluster_name        = var.karpenter_cluster_name
}

module "storage" {
  count  = var.enable_artifact_storage ? 1 : 0
  source = "./modules/storage"
}

module "secrets" {
  count            = var.enable_secrets_manager ? 1 : 0
  source           = "./modules/secrets"
  enable_karpenter = local.enable_karpenter_stack
}

module "iam" {
  count                      = local.enable_shared_iam ? 1 : 0
  source                     = "./modules/iam"
  artifacts_bucket_arn       = module.storage[0].bucket_arn
  github_secrets_arn         = module.secrets[0].aws_secrets_arn
  github_actions_secrets_arn = module.secrets[0].github_actions_secrets_arn
  mlflow_basic_auth_arn      = module.secrets[0].production_secrets_arn

  enable_github_oidc     = var.enable_github_oidc
  enable_karpenter       = local.enable_karpenter_stack
  karpenter_cluster_name = var.karpenter_cluster_name
  karpenter_k3s_token_secret_arn = (
    local.enable_karpenter_stack ? module.secrets[0].karpenter_k3s_token_secret_arn : ""
  )
}

module "compute" {
  count                = local.enable_k3s_compute_stack ? 1 : 0
  source               = "./modules/compute"
  public_subnet_1a_id  = module.network[0].public_subnet_1a_id
  private_subnet_1a_id = module.network[0].private_subnet_1a_id
  master_sg_id         = module.security[0].master_sg_id
  worker_sg_id         = module.security[0].worker_sg_id
  worker_profile_name  = module.iam[0].worker_profile_name

  key_name              = var.key_name
  master_instance_type  = var.master_instance_type
  master_volume_size    = var.master_volume_size
  worker_instance_count = var.worker_instance_count
  worker_instance_type  = var.worker_instance_type
  worker_volume_size    = var.worker_volume_size
}

module "dns" {
  count                        = (var.enable_acm_certificate || local.enable_karpenter_stack) ? 1 : 0
  source                       = "./modules/dns"
  domain_name                  = var.domain_name
  enable_acm_certificate       = var.enable_acm_certificate
  enable_karpenter_private_dns = local.enable_karpenter_stack
  vpc_id                       = local.enable_karpenter_stack ? module.network[0].vpc_id : ""
  master_private_ip            = local.enable_karpenter_stack ? module.compute[0].master_private_ip : ""
  karpenter_private_zone_name  = "internal.${var.domain_name}"
}

module "alb" {
  count                = local.enable_alb_stack ? 1 : 0
  source               = "./modules/alb"
  vpc_id               = module.network[0].vpc_id
  public_subnet_ids    = [module.network[0].public_subnet_1a_id, module.network[0].public_subnet_1b_id]
  lb_sg_id             = module.security[0].lb_sg_id
  worker_instance_ids  = module.compute[0].worker_instance_ids
  certificate_arn      = module.dns[0].certificate_arn
  idle_timeout_seconds = var.alb_idle_timeout_seconds
}

check "nat_gateway_requires_network" {
  assert {
    condition     = !var.enable_nat_gateway || var.enable_network
    error_message = "enable_nat_gateway requires enable_network=true."
  }
}

check "k3s_compute_dependencies" {
  assert {
    condition = !var.enable_k3s_compute || (
      var.enable_network &&
      var.enable_nat_gateway &&
      var.enable_artifact_storage &&
      var.enable_secrets_manager
    )
    error_message = "enable_k3s_compute requires network, NAT Gateway, artifact storage and Secrets Manager to be enabled."
  }
}

check "alb_dependencies" {
  assert {
    condition = !var.enable_alb || (
      var.enable_network &&
      var.enable_k3s_compute &&
      var.enable_acm_certificate
    )
    error_message = "enable_alb requires network, K3s compute and the ACM certificate to be enabled."
  }
}

check "karpenter_dependencies" {
  assert {
    condition = !var.enable_karpenter || (
      var.enable_network &&
      var.enable_nat_gateway &&
      var.enable_k3s_compute
    )
    error_message = "enable_karpenter requires network, NAT Gateway and the static K3s cluster to be enabled."
  }
}

check "github_oidc_dependencies" {
  assert {
    condition = !var.enable_github_oidc || (
      var.enable_artifact_storage &&
      var.enable_secrets_manager
    )
    error_message = "enable_github_oidc requires artifact storage and Secrets Manager because the deployment role references both resources."
  }
}

moved {
  from = module.network
  to   = module.network[0]
}

moved {
  from = module.security
  to   = module.security[0]
}

moved {
  from = module.storage
  to   = module.storage[0]
}
