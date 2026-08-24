# Bootstrap sequence

1. Provision network, security, storage, secrets, IAM, compute/load balancing, and DNS through Terraform as enabled.
2. Obtain non-secret Terraform outputs needed for inventory.
3. Build/verify Ansible inventory for K3s server and workers.
4. Run host preparation.
5. Initialize the K3s server with its private DNS TLS SAN; publish the agent
   token version to the Terraform-owned Secrets Manager container and securely
   distribute it to static workers.
6. Join worker nodes and verify node readiness.
7. Install pinned Argo CD on static workers and create the public root Application.
8. Let the root reconcile child Applications in lifecycle order: cluster namespaces,
   pinned core add-ons, cluster storage/secret-store/policy, shared platform
   data/services, execution, workloads and edge.
9. Validate storage, database, messaging, control workloads, ingress, and monitoring.
10. Let Argo CD reconcile Karpenter capacity, then validate CPU capacity and
    opt into the GPU smoke test only when AWS quota is effective.

Maintain a single owner for each operator/resource. Terraform provisions cloud primitives; Ansible bootstraps hosts and Argo CD; GitOps owns operators and application state after bootstrap.
