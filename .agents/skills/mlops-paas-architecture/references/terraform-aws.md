# Terraform AWS

The root composition wires modules for:

- `network`: VPC, public/private subnets, routes, NAT/internet gateways.
- `security`: security groups and traffic boundaries.
- `storage`: S3 buckets and storage configuration.
- `secrets`: Secrets Manager resources, not secret values in state/source.
- `iam`: instance, workload, registry, and automation permissions.
- `compute`: control/worker instances or related bootstrap compute.
- `alb`: listeners, target groups, certificates, and public service routing.
- `dns`: Route53 records.
- Karpenter dependencies: queues, node roles/profiles, discovery tags, the
  agent-token secret container, and private Route53 DNS for the K3s API.

Inspect `variables.tf`, feature flags, `main.tf`, and outputs together. Disabled optional modules must not be referenced unconditionally. Apply least privilege and avoid wildcard Secrets Manager/S3/IAM permissions.

## Root feature flags

Persistent foundation resources use `enable_artifact_storage`, `enable_secrets_manager`, `enable_github_oidc`, and `enable_acm_certificate`. Runtime resources use `enable_network`, `enable_nat_gateway`, `enable_k3s_compute`, `enable_alb`, and `enable_karpenter`.

Current dependencies are enforced by root `check` blocks:

- K3s compute requires network, NAT, artifact storage, and Secrets Manager.
- ALB requires network, K3s compute, and ACM.
- Karpenter requires network, NAT, and the static K3s cluster.
- GitHub OIDC currently requires artifact storage and Secrets Manager because its IAM policy references both.

Turning a flag off proposes resource destruction; it is not a pause mechanism. Review the plan and protect or separate persistent foundation state before disabling S3 or Secrets Manager.

The four repository-managed Secrets Manager containers intentionally use
`recovery_window_in_days = 0`. A Terraform destroy permanently deletes their
metadata and stored versions. After recreation, `scripts/push_secrets_to_aws.py`
publishes the three application secret values; Ansible publishes the K3s agent
token after server bootstrap. Never destroy this module unless the required
source values are available.

Terraform owns only the `mlops/k3s-agent-token` secret metadata. Ansible writes
its runtime version after K3s starts, so the token must never enter Terraform
configuration, plan, outputs, or state.

Do not edit generated state, commit tfvars containing secrets, or infer that AWS EC2 is still the only target; the deployment may use external VMs while retaining S3/Secrets Manager.
