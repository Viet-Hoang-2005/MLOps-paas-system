---
name: mlops-paas-security
description: Review or implement security-sensitive changes involving authentication, tenant isolation, UUID APIs, webhooks, capabilities, presigned storage, untrusted workloads, secrets, IAM, Harbor, network exposure, or infrastructure. Use alongside any affected domain skill.
---

# MLOps PaaS Security

Use this skill to review, design, or implement security-sensitive mechanisms across authentication, authorization, tenant boundaries, untrusted workload isolation, storage capabilities, and infrastructure policies.

Never include passwords, tokens, private keys, real `.env` values, SSH credentials, or secret payloads in source code, skills, logs, commands, or answers.

## Workflow

1. Identify actors, assets, trust boundaries, resource UUIDs, and public vs. internal entrypoints.
2. Read [trust-boundaries.md](references/trust-boundaries.md), [identity-and-tenancy.md](references/identity-and-tenancy.md), [capabilities-and-storage.md](references/capabilities-and-storage.md), and [security-review-checklist.md](references/security-review-checklist.md).
3. Verify tenant ownership at every database query, selector, and callback endpoint.
4. Enforce principle of least privilege across IAM policies, token TTLs, and S3 Presigned URLs.
5. Treat all user-uploaded training code, datasets, and custom dependencies as **Hostile Untrusted Workloads**.
6. Distinguish active reconciled controls (Kyverno Cosign verification, Traefik proxy headers, Loki signed cursors) from inactive drafts.
7. Preserve existing security invariants and avoid regressions.

## Core Security Invariants

- **Untrusted Training Sandbox:** Container `training-runner` executes user code without AWS credentials, database passwords, or cluster admin tokens. It communicates solely via short-lived Capability Tokens and Presigned S3 URLs.
- **Inference Gateway Isolation:** Model workers (`machine-learning-serving`, `deep-learning-serving`) reside in protected internal networks with zero public ingress. `model-server` is the sole trusted authentication and authorization gateway (verifies RS256 JWT via Control Plane JWKS or Project API Key).
- **Supply Chain Security:** Kyverno enforces keyless Cosign signature verification on all platform images (`registry.mlops-nids-nt114.id.vn/mlops-paas/*`) produced by GitHub Actions CD on `main`. Container builds use Kaniko for rootless builds without mounting the Docker socket.
- **Safe Archive Extraction:** Model Packager and Training Runner enforce strict path sanitization against **Zip/Tar Slip** (rejecting `..`, absolute paths, and external symlinks).
- **Database Segregation:** Background analytical workloads (Evidently) connect strictly via `DB_HOST_RO` using a read-only PostgreSQL role.
- **Log Security & Anti-Leakage:** Production Loki logs are proxied through Control Plane with signed task-bound cursors, preventing cross-tenant LogQL queries. Sensitive values (tokens, credentials, API keys) are masked before emission.

## Validation

- Run focused security/tenant isolation tests:
  ```bash
  pytest services/control-plane/src/apps/auth/tests/
  pytest services/control-plane/src/apps/access/tests/
  pytest k8s/validate/tests/test_execution_security.py
  ```
- Run leak scan and verify no unmasked credentials or private keys appear in git diff:
  ```bash
  git diff --check
  ```
