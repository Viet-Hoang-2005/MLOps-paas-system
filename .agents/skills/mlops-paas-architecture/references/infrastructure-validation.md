# Infrastructure validation

Run from the relevant directory:

```bash
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
ansible-playbook --syntax-check <playbook>
ansible-playbook --check --diff <playbook>
```

Use targeted Kustomize/Helm validation from the deployment skill for cluster resources.

## Review checklist

- Feature-flag combinations do not create invalid references.
- Outputs expose no credentials or private key material.
- Security groups and listeners match intended public/private surfaces.
- IAM actions/resources are minimal and scoped.
- S3/Secrets Manager policies match tenant/trusted workload boundaries.
- Inventory and roles remain idempotent.
- Terraform plan is reviewed before any authorized apply.
- Destroy, import, state migration, credential rotation, and production execution require explicit user authorization.
