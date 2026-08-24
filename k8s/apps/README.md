# Static workload overlays

`base/<service>` contains environment-neutral Kubernetes resources. Base image
references use only the logical image name and base packages are never direct
Argo CD sources.

`overlays/production/<service>` is the deployable production package for each
independent workload Application. The production overlay owns the registry and
Git SHA image tag; GitHub Actions promotes only the service whose source changed.

Add future environments as sibling overlays, for example
`overlays/dev/<service>` and `overlays/staging/<service>`. Keep one Kustomization
and one Argo CD Application per service so promotion and rollback remain
independent.
