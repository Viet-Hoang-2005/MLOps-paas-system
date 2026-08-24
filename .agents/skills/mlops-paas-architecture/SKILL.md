---
name: mlops-paas-architecture
description: Plan, implement, or validate AWS infrastructure, Terraform modules, Ansible roles, K3s bootstrap, and the handoff to GitOps. Use for VPC, compute, storage, IAM, load balancing, DNS, K3s node, or cluster bootstrap changes.
---

# MLOps PaaS infrastructure architecture

## Workflow

1. Inspect live Terraform modules, variables, outputs, Ansible inventory/roles, and consuming manifests.
2. Read [terraform-aws.md](references/terraform-aws.md) or [ansible-k3s.md](references/ansible-k3s.md), plus [bootstrap-sequence.md](references/bootstrap-sequence.md) for cross-layer changes.
3. Trace feature flags and dependency order before changing a module.
4. Keep credentials and secret values out of plans, output, logs, and skills.
5. Use the checks in [infrastructure-validation.md](references/infrastructure-validation.md).
6. Never run apply, destroy, credential rotation, or production mutation without explicit authorization.
7. Preserve user changes and avoid unrelated infrastructure refactors.
8. Update this skill if provisioning/bootstrap ownership changes.

Load `$mlops-paas-security` for IAM, networks, public exposure, or secrets, and `$mlops-paas-deployment` for resources reconciled after bootstrap.

For cross-layer changes also load `$mlops-paas-overview`. Treat Terraform, Ansible, tests/checks, and consuming manifests as more authoritative than README or architecture prose; reconcile conflicts explicitly. Never embed passwords, tokens, private keys, real environment values, or SSH credentials.
