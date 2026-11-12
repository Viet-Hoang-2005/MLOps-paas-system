# Kubeflow Trainer v2 GitOps contract

The controller is installed by the direct Helm Application
`mlops-prod-addon-kubeflow-trainer` at wave -24. It renders the official
`ghcr.io/kubeflow/charts/kubeflow-trainer` chart 2.3.0, including JobSet 0.12.0,
in `kubeflow-system`. JobSet's image is explicitly pinned to its released image;
the chart's built-in runtime installer and data cache are disabled.

`mlops-prod-addon-training-runtimes` owns the raw Git directory
`k8s/argo/runtimes/training` at wave -22. The execution Kustomization does not
include this directory. This prevents shared ownership and waits for controller
readiness before admitting the custom runtime. Certificate drift exclusions
cover only the rendered webhook CA bundles and the two controller-owned
certificate Secrets, not webhook configuration or arbitrary Secrets.

The platform runtime `mlops-paas-single-node` uses PlainML and one `node`
container, without a framework-specific launcher. CPU/GPU TrainJobs reference
the same runtime. Resources and env use `spec.trainer`; ownership and scheduling
use `runtimePatches` owned by `mlops-paas.io/control-plane`. Jobs cannot restart
automatically: the platform's retry operation creates a new Training Job.

`prepare-input` writes the Input volume; `node` mounts it read-only. Work,
model and output use separate writable volumes matching the runner's
`/workspace/work`, `/workspace/model` and `/workspace/output` paths. User code
continues to use the existing environment contract and does not need a new SDK.
Image promotion updates init and main together in the runtime, not the Helm
controller image or an embedded Workflow manifest.

Argo creates the TrainJob, then a trusted wait step checks conditions by type
(`Complete`/`Failed`) rather than array position. The Workflow and TrainJob are
in different namespaces, so no cross-namespace owner reference is created.
The execution watcher checks all tenant/job labels, captures `node` timestamps,
and persists timing on the owned Workflow before foreground cleanup. Cleanup
is pending until TrainJob, JobSet, Jobs and Pods are gone. Unknown runtime timing
keeps the quota reservation. A newly created pre-submit tombstone can prove a
job never started; the signed internal observation then releases its reservation
without charging runtime. This flag is not a public training API field.

## Offline verification

Install the Python dependencies from `k8s/verify/requirements.txt` and provide
Helm v3 and kubectl/Kustomize on PATH.

```sh
python -m pytest k8s/verify/validate/ -q
python -m ruff check services/
git diff --check
```

These tests do not contact a Kubernetes API server. They need OCI registry access
to fetch the pinned chart and validate the runtime/TrainJob/JobSet structural
schemas. Admission webhooks, CEL rules and controller reconciliation still need
the authorized staging acceptance below.

## Staging acceptance (not performed by an offline refactor)

Before promotion, confirm production has no v1 workload requiring a transition.
Do not automatically delete legacy CRDs. Existing database/storage history and
the Docker execution backend are retained.

After the GitOps controller/runtime Applications are Synced and Healthy, run CPU,
T4 x1 and A10G x1 jobs through the platform, including jobs without a Project.
Verify the generated ownership labels, requests/limits, node instance type and
GPU UUID; confirm Input writes fail and Work/model/output writes succeed.
Verify model upload before completion, live cAdvisor/DCGM metrics, deadline
failure, API/worker outages, duplicate events, cancel-before-submit and cancel
during execution. Confirm the entire workload tree is gone and quota settles
only after confirmed stop.

The Ansible isolated smoke namespace uses a small namespace-owned TrainingRuntime
and public CUDA image to test controller/scheduling readiness independently of
private runner credentials and storage capabilities. It does not replace the
end-to-end platform acceptance above.
