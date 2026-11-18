# GitOps and Kustomize

- Begin at [production kustomization](../../../../k8s/gitops/production/kustomization.yaml). Its Application sets are grouped into addons, cluster, platform, execution and workloads. Read Application annotations and source refs for actual dependency order and placement.
- Follow each Application's source to the base or production overlay and its matching AppProject. For Helm sources inspect the chart version, values and allowlisted destination/source before changing defaults.
- Inspect the rendered resource for final namespace, labels, resources, image, and overrides. Keep the chart/operator or workload under one installation owner. Where a controller mutates fields, verify the current ignore rules before adding new exclusions.
- [CD](../../../../.github/workflows/cd.yml) is the source for image build, signing and GitOps promotion. Follow image changes through both training containers and the packager's serving base references where relevant. Verify promotion with [validate_cd_promotion.py](../../../../k8s/verify/validate/validate_cd_promotion.py).
