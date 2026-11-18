---
name: mlops-paas-security
description: Review or change tenant authorization, callbacks, capabilities, signed storage, secrets, workload isolation, IAM, or network exposure.
---

# MLOps PaaS Security

Trace the principal, tenant, resource UUID and operation across the changed path. Identify which credential authorizes each hop and which component owns the corresponding state. Preserve the distinction between trusted lifecycle reporters and tenant processes.

- [Trust boundaries](references/trust-boundaries.md) and [Identity and tenancy](references/identity-and-tenancy.md) cover principals and authorization.
- [Capabilities and storage](references/capabilities-and-storage.md) covers callback scope, token lifetime and presigned objects.
- [Workload isolation](references/workload-isolation.md) covers execution of tenant code and artifacts.
- [Secrets, IAM and network](references/secrets-iam-and-network.md) covers infrastructure and credential delivery.
- [Security review checklist](references/security-review-checklist.md) helps choose relevant denial and replay tests.

Start with the domain's existing tests. Match negative cases to the changed boundary, such as wrong-tenant UUIDs, expired tokens, late callbacks or access to private Output. Use synthetic credentials in examples and test fixtures.
