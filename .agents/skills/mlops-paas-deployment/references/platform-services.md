# Platform services

Start with the relevant Application under [production GitOps](../../../../k8s/gitops/production/applications). Addons own controllers; platform Applications own backing services and routing. Consult Application sources and sync waves for the actual installation and dependencies.

- Change chart resources in the owning Application and check the rendered container-level requests and limits.
- For capacity changes, trace the matching Karpenter Application and NodePool/NodeClass. Use [Trainer v2](../../../../docs/dev/trainer-v2.md) for the training runtime boundary.
- Verify workload health after CD promotes images. Compare core, training and workloads verification scopes in [Ansible site.yml](../../../../ansible/site.yml).
