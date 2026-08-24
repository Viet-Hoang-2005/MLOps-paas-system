# Workload isolation

Training and dynamic model workers execute tenant-controlled artifacts.

Required controls:

- Dedicated `user-jobs` namespace and least-privilege service accounts.
- Disable service-account token automount unless required.
- Pod Security admission/profile and restrictive security contexts.
- Default-deny ingress and egress with explicit DNS/storage/callback exceptions.
- Resource quotas, limits, timeouts, and process/container cancellation.
- Block cloud instance metadata from pods.
- Prefer gVisor, Kata, or equivalent sandboxing for hostile code.
- Separate trusted reporter/control containers from tenant code.
- No `envFrom` shared application Secret in tenant workloads.

Current repository security manifests must be checked for actual root/overlay inclusion; an unreferenced NetworkPolicy provides no protection.
