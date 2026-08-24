---
name: mlops-paas-overview
description: Orient cross-cutting work in the MLOps PaaS repository, including component ownership, system planes, identifiers, state ownership, and upload, training, deployment, inference, and drift lifecycles. Use before work that spans multiple services or when the correct domain skill is unclear.
---

# MLOps PaaS overview

Use this skill to establish system context before changing a cross-service contract.

Never embed passwords, tokens, private keys, real environment values, or SSH credentials in skills or source.

## Workflow

1. Inspect the live files involved in the request. Treat code, migrations, tests, manifests, and workflows as authoritative.
2. Read [repo-map.md](references/repo-map.md) to identify ownership.
3. Read [system-architecture.md](references/system-architecture.md) for state and plane boundaries.
4. Read only the relevant lifecycle in [lifecycles.md](references/lifecycles.md).
5. Read [cross-service-contracts.md](references/cross-service-contracts.md) before changing IDs, storage paths, callbacks, images, or routing.
6. Load every affected domain skill. Also load `$mlops-paas-security` for tenancy, credentials, webhooks, IAM, untrusted workloads, or public exposure.
7. Reconcile stale README, `.env.example`, or architecture prose with implementation rather than copying it.
8. Preserve user changes and avoid unrelated refactors.

## Domain routing

- Web UI, routing, state, design, or i18n: `$mlops-paas-frontend`
- Python services or API contracts: `$mlops-paas-backend`
- Docker Compose or environment configuration: `$mlops-paas-environment`
- Terraform, AWS, Ansible, or K3s bootstrap: `$mlops-paas-architecture`
- K3s workloads, GitOps, Argo, or platform operations: `$mlops-paas-deployment`
- Any security-sensitive change: `$mlops-paas-security`

## Invariants

- PostgreSQL and S3 are lifecycle truth. Redis is transient queue, cache, and runtime-log state.
- Public resources use UUIDs; integer database keys stay internal.
- Keep tenant, project, version, build, deployment, training-job, monitor, and run IDs distinct.
- Successful image builds create immutable registry versions. Project metadata remains latest-only.
- Do not introduce the legacy `MODEL_ID` environment contract.
- When intentionally changing an architectural contract, update the applicable skill references in the same change.

## Validation

Run the smallest affected domain checks. For documentation-only skill changes, validate each skill with `quick_validate.py` and run `git diff --check`.
