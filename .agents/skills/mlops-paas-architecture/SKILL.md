---
name: mlops-paas-architecture
description: Trace and change Terraform AWS or Cloudflare infrastructure, Ansible provisioning, and K3s bootstrap up to the GitOps handoff.
---

# MLOps PaaS Infrastructure

Find the first failing layer in the chain from Terraform outputs through Ansible inventory and K3s bootstrap to Argo CD. Check the owner of the resource before editing a module or role.

- [Terraform AWS](references/terraform-aws.md) maps compute, network, IAM, storage and the Cloudflare handoff.
- [Ansible and K3s](references/ansible-k3s.md) maps inventory, inputs, playbook roles and the control-host requirements.
- [Bootstrap sequence](references/bootstrap-sequence.md) explains the handoff and verification stages.
- [Infrastructure validation](references/infrastructure-validation.md) gives offline checks and review points for Terraform and Ansible.

Use the [deployment skill](../mlops-paas-deployment/SKILL.md) for resources managed by Argo CD after bootstrap. Keep offline validation separate from provisioning, applying, or verifying against a live environment.
