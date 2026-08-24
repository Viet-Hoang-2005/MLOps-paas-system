---
name: mlops-paas-security
description: Review or implement security-sensitive changes involving authentication, tenant isolation, UUID APIs, webhooks, capabilities, presigned storage, untrusted workloads, secrets, IAM, Harbor, network exposure, or infrastructure. Use alongside any affected domain skill.
---

# MLOps PaaS security

## Workflow

1. Identify actors, assets, trust boundaries, resource UUIDs, and public/internal entry points.
2. Inspect current auth, selectors, serializers, tasks, manifests, IAM, network policies, tests, and logs.
3. Read the relevant references, starting with [trust-boundaries.md](references/trust-boundaries.md) and [security-review-checklist.md](references/security-review-checklist.md).
4. Verify tenant ownership at every lookup and callback boundary.
5. Minimize credentials, permissions, URL scope, token lifetime, network access, and log exposure.
6. Treat tenant training and model code as hostile.
7. Distinguish controls that are implemented and reconciled from desired manifests that are not active.
8. Preserve user changes and avoid unrelated refactors.
9. Update this skill when intentionally changing a security invariant.

Never include passwords, tokens, private keys, real `.env` values, SSH credentials, or secret payloads in source, skills, logs, commands, or answers.

For cross-service reviews also load `$mlops-paas-overview` and every affected domain skill. Treat code, migrations, tests, rendered manifests, and IAM/network policy as more authoritative than README or architecture prose; reconcile conflicts explicitly.

## Validation

Run focused authorization/tenant/callback tests, render affected manifests, inspect effective IAM/network/secret references, and perform a leak scan before completion.
