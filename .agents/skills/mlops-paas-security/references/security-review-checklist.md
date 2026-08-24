# Security review checklist

## Identity and authorization

- Is every public lookup tenant scoped?
- Are UUID type, ownership, access mode, and version/project relationship validated?
- Are API keys/JWT/OAuth failure modes covered?

## Callbacks and async work

- Is the callback authenticated, resource-bound, expiring where applicable, and idempotent?
- Can replay or a late callback revive a cancelled/deleting resource?
- Is terminal state derived from a trusted reporter?

## Storage and uploads

- Are URLs operation/object scoped with short TTL?
- Are archive traversal, symlink, size, and content risks handled?
- Can deletion escape the tenant/project prefix?

## Execution

- Does any untrusted pod receive shared secrets, credentials, metadata access, privileged mounts, or excessive egress?
- Are namespace, service account, Pod Security, quotas, and NetworkPolicies both defined and reconciled?

## Infrastructure

- Are IAM and security groups least privilege?
- Are secret values absent from state/source/logs?
- Are public services intentionally exposed with TLS and limits?

## Completion

- Add focused negative tests.
- Render effective manifests and inspect references.
- Scan the diff for credentials/private keys.
- Update the relevant skill when a security contract changes.
