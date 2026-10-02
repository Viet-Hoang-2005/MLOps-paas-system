# Terraform AWS Infrastructure

The Terraform composition (`infra/`) provisions IaaS cloud resources across 9 dedicated modules:

## Module Breakdown

1. **`network`:** VPC (`10.0.0.0/16`), public & private subnets across multiple AZs, route tables, Internet Gateway, and NAT Gateway.
2. **`security`:** Security groups establishing strict boundaries:
   - ALB Security Group: Inbound HTTP (80) & HTTPS (443) from internet.
   - Master Node Security Group: Inbound SSH (22) from internet, K3s API (6443) from VPC/workers, NodePort/Traefik from ALB.
   - Worker Node Security Group: Inbound all traffic from Master and fellow Workers, NodePort from ALB.
3. **`storage`:** AWS S3 buckets:
   - `artifacts_bucket` (`mlops-paas-artifacts`): S3 bucket for model weights, snapshots, datasets, and reports. Versioning enabled, public access blocked, CORS configured.
   - `runtime_logs` (`mlops-paas-runtime-logs`): Dedicated bucket for production Loki task logs. Uses `force_destroy = true` for clean teardown during terraform destroy.
4. **`secrets`:** AWS Secrets Manager containers with `recovery_window_in_days = 0` (secret metadata only, not values in state).
5. **`iam`:** Instance profiles, worker roles, Karpenter node roles, and GitHub Actions OIDC federation.
6. **`compute`:** Ubuntu 22.04 LTS EC2 instances for K3s Master (public IP/bastion) and static Workers (private IPs).
7. **`alb`:** AWS Application Load Balancer with listeners, health check target groups, and idle timeout 600s.
8. **`dns`:** Route 53 private and public zones with ACM SSL certificates.
9. **Karpenter Dependencies:** SQS Interruption Queue and EventBridge rules for EC2 Spot rebalance / termination notices.

## Deployment Modes

1. **Full Production:** All modules enabled via `terraform.tfvars`. Deploys VPC, EC2 cluster, ALB, S3, Secrets Manager, and IAM.
2. **S3-Only for Local Docker Compose:** Minimal deployment using `s3-only.tfvars`:
   ```bash
   terraform apply -var-file="s3-only.tfvars"
   ```
   Provisions only the S3 artifacts bucket. In this mode, `worker_private_ips` outputs `null` (not `[]`) to keep the plan clean.

## Teardown & Dynamic EBS Cleanup

- Dynamic EBS volumes created by Kubernetes CSI drivers (e.g. CloudNativePG, Prometheus, Redis PVCs) are not managed by Terraform.
- Before running `terraform destroy`, all dynamic PVCs/EBS volumes in AWS must be deleted, or cleaned up via AWS CLI post-destroy to prevent orphaned resources.
