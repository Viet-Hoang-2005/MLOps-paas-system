# Infrastructure validation

Run from the relevant directory:

```bash
# Terraform AWS
cd terraform/aws && terraform fmt -check -recursive && terraform init -backend=false && terraform validate

# Terraform Cloudflare
cd terraform/cloudflare && terraform fmt -check -recursive && terraform init -backend=false && terraform validate

# Ansible
cd ansible
ansible-playbook --syntax-check -i localhost, site.yml
```

Match dependency setup and syntax checks to [CI](../../../../.github/workflows/ci.yml). Use targeted Kustomize/Helm checks for cluster resources. Ansible check mode may contact inventory hosts; use it only within authorized live scope.

## Review checklist

- Feature-flag combinations do not create invalid references.
- Outputs expose no credentials or private key material.
- Security groups and listeners match intended public/private surfaces.
- IAM actions/resources are minimal and scoped.
- S3/Secrets Manager policies match tenant/trusted workload boundaries.
- Inventory and roles remain idempotent.
- Terraform plan is reviewed before any authorized apply.
- Destroy, import, state migration, credential rotation, and production execution require explicit user authorization.
