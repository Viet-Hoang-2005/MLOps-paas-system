# Argo execution

Start at `services/control-plane/src/infrastructure/execution/argo_backends.py`, then follow the Argo EventSource/Sensor to the template under `k8s/argo/workflows/`. Confirm the event identifiers, workload labels, callback capability and service account at each hop. Workflows run in `mlops-paas-execution`; training resources run in `mlops-paas-training`.

## Build and logs

The current [build Workflow](../../../../k8s/argo/workflows/build/workflow.yaml) prepares the package, builds via Kaniko into `/workspace/image.tar`, pushes from that archive in a separate step, and reports status. Verify the live template before changing the stages or installing cache.

For missing Build logs, compare the Workflow's pod label `mlops-paas.io/build-id` with Alloy's discovery label `__meta_kubernetes_pod_label_mlops_paas_io_build_id` in [alloy.yaml](../../../../k8s/gitops/production/applications/addons/alloy.yaml). Then check the emitted Loki labels against query construction in [runtime_logs.py](../../../../services/control-plane/src/infrastructure/runtime_logs.py) and the owning API. Check the Build UUID and tenant scope; task log availability and Build completion are separate observations. Local builds use the Docker log path.

## Training and runtime lifecycle

The [training Workflow](../../../../k8s/argo/workflows/training/workflow.yaml) creates Kubeflow Trainer v2 `TrainJob` resources. Follow the managed runtime and workload tree through [Trainer v2](../../../../docs/dev/trainer-v2.md). Preserve job/tenant ownership labels, optional Project identity, trusted preparation and read-only Input. Keep init and main runner image references aligned and out of tenant control.

For deploy/delete/reconcile, follow the owning workflow's trusted status reporter and scope, then verify delayed results and cleanup fences against the Control Plane. See [operations and validation](operations-and-validation.md) for render and live boundaries.
