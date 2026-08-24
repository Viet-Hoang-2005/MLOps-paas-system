# Secrets, IAM, registry, and network

- Local secrets live in an ignored `.env`; production uses Secrets Manager and External Secrets for trusted workloads.
- Rotate credentials that were exposed to tenant code or logs.
- Never commit SSH private keys, OAuth secrets, JWT keys, AWS keys, Harbor robot credentials, or webhook secrets.
- IAM policies must scope S3 buckets/prefixes, Secrets Manager ARNs, registry operations, and infrastructure actions.
- Node IAM must not grant every pod broad secret access; use workload identity/isolated roles where supported.
- Restrict metadata service access and hop behavior.

For AWS K3s bootstrap, the private SSH key stays at `~/.ssh/aws_key` on the WSL
control host with mode `0600`. K3s kubeconfig and join token must be protected
with `no_log`; the token is written to Secrets Manager from the existing WSL AWS
session, never by copying AWS access keys to the server. Karpenter nodes require
IMDSv2 and hop limit 1.

The current rollout intentionally defers custom NetworkPolicies and PDBs until
core stability. Treat that as an explicit security gap and do not claim tenant
network isolation is active merely because manifests exist under `k8s/security`.

Harbor automation uses a least-privilege robot account. Store image digest as immutable identity and verify signatures where the pipeline supports them.

Expose only required services. Large artifact/registry traffic needs an ingress/load-balancer path sized for uploads; administrative UIs may use a tunnel. Apply TLS, request limits, authentication, and source restrictions at each public boundary.
