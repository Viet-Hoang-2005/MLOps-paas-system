---
name: mlops-paas-architecture
description: Plan, implement, or validate cloud infrastructure (Terraform for AWS & Cloudflare), Ansible roles, K3s bootstrap, and the handoff to GitOps. Use for VPC, compute, storage, IAM, load balancing, Cloudflare DNS/Tunnel/Security, K3s node, or cluster bootstrap changes.
---

# MLOps PaaS Infrastructure Architecture

Use this skill to plan, implement, review, or troubleshoot cloud infrastructure (Terraform for AWS & Cloudflare), host OS configuration, K3s cluster bootstrap (Ansible), and the transition to GitOps (Argo CD).

Never embed passwords, tokens, private keys, real environment values, or SSH credentials in skills, code, or outputs.

## Workflow

1. Inspect live Terraform configurations (`terraform/aws/`, `terraform/cloudflare/`), variables, outputs, and Ansible playbooks/roles (`ansible/`).
2. Read [terraform-aws.md](references/terraform-aws.md), [ansible-k3s.md](references/ansible-k3s.md), and [bootstrap-sequence.md](references/bootstrap-sequence.md).
3. Trace feature flags (`enable_artifact_storage`, `enable_k3s_compute`, etc.) and dependency order before modifying modules.
4. Support both deployment modes:
   - *Full Production:* AWS infrastructure (`terraform/aws/`) + Cloudflare DNS/Tunnel/Security (`terraform/cloudflare/`).
   - *Local S3-Only:* Provisioning only the S3 bucket for local Docker Compose (`cd terraform/aws && terraform apply -var-file="s3-only.tfvars"`).
5. Use checks in [infrastructure-validation.md](references/infrastructure-validation.md).
6. Never execute `terraform apply`, `destroy`, credential rotation, or production mutations without explicit user authorization.
7. Preserve user modifications and avoid unrelated infrastructure refactors.

## Core Infrastructure Invariants

- **Handoff Chain:** `Terraform (IaaS: AWS & Cloudflare)` $\rightarrow$ `Ansible (Host OS & K3s Bootstrap)` $\rightarrow$ `Argo CD (GitOps Core)`.
- **Dynamic Inventory:** `ansible/inventory/terraform.py` parses `terraform/aws` output dynamically (`terraform output -json`); zero hardcoded IP addresses.
- **Security Boundaries:** Master node acts as SSH Bastion; private worker nodes are accessed solely via SSH ProxyJump. Public TLS terminates at AWS ALB and Cloudflare Edge.
- **S3 Bucket Lifecycle:** Both `artifacts_bucket` and `runtime_logs` use `force_destroy = true` to allow clean teardown when authorized.

## Validation

```bash
# Terraform AWS
cd terraform/aws
terraform fmt -check -recursive
terraform validate

# Terraform Cloudflare
cd terraform/cloudflare
terraform fmt -check -recursive
terraform validate

# Ansible
cd ansible
ansible-playbook -i inventory/terraform.py playbooks/site.yml --syntax-check
```
