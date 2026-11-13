"""Pinned chart schema and lifecycle regression checks (no cluster)."""
import copy
import importlib.util

import pytest
from jsonschema import Draft202012Validator

from ..trainer import ROOT, patch_pod, runtime, trainjob

SPEC = importlib.util.spec_from_file_location("trainer_operations", ROOT / "k8s/argo/workflows/operations/scripts/job_ops.py")
ops = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ops)
PAYLOAD = {"kind": "training", "job_id": "11111111-1111-1111-1111-111111111111", "project_id": "",
           "tenant_id": "T-22222222-2222-2222-2222-222222222222"}
NAME, LABELS = ops.identity(PAYLOAD, "training")


@pytest.mark.validate
def validate_trainer_chart_and_schemas(context):
    application = next(a for a in context.applications if a["metadata"]["name"] == "mlops-prod-addon-kubeflow-trainer")
    resources = context.render_helm(application, include_crds=True)
    crds = {r["spec"]["names"]["kind"]: r for r in resources if r["kind"] == "CustomResourceDefinition"}
    assert {"TrainJob", "ClusterTrainingRuntime", "TrainingRuntime", "JobSet"} <= crds.keys()
    controllers = [r for r in resources if r["kind"] == "Deployment"]
    assert len(controllers) == 2
    images = {c["image"] for r in controllers for c in r["spec"]["template"]["spec"]["containers"]}
    assert images == {"registry.k8s.io/jobset/jobset:v0.12.0", "ghcr.io/kubeflow/trainer/trainer-controller-manager:v2.3.0"}
    assert all(not r["metadata"].get("annotations", {}).get("helm.sh/hook") for r in resources)
    for r in controllers:
        assert r["spec"]["template"]["spec"]["nodeSelector"] == {"workload-type": "worker"}
    samples = [runtime(), trainjob("cpu-train-job"), trainjob("gpu-train-job", "t4"), trainjob("gpu-train-job", "a10g")]
    for sample in samples:
        version = next(v for v in crds[sample["kind"]]["spec"]["versions"] if v["name"] == "v1alpha1")
        Draft202012Validator(version["schema"]["openAPIV3Schema"]).validate(sample)
    jobset = {"apiVersion": "jobset.x-k8s.io/v1alpha2", "kind": "JobSet", "metadata": {"name": NAME},
              "spec": runtime()["spec"]["template"]["spec"]}
    version = next(v for v in crds["JobSet"]["spec"]["versions"] if v["name"] == "v1alpha2")
    Draft202012Validator(version["schema"]["openAPIV3Schema"]).validate(jobset)
    # Ignore only controller-generated certificate fields, and only on rendered resources.
    identities = {(r["kind"], r["metadata"]["name"]) for r in resources}
    for rule in application["spec"]["ignoreDifferences"]:
        assert (rule["kind"], rule["name"]) in identities
        assert rule.get("jsonPointers") == ["/data"] or rule.get("jqPathExpressions") == [".webhooks[]?.clientConfig.caBundle"]


@pytest.mark.validate
def validate_runtime_single_node_and_labels():
    template = runtime()["spec"]["template"]["spec"]
    assert template["failurePolicy"]["maxRestarts"] == 0
    job = template["replicatedJobs"][0]
    assert job["replicas"] == 1 and job["template"]["spec"]["backoffLimit"] == 0
    assert job["template"]["spec"]["template"]["spec"]["restartPolicy"] == "Never"
    for name in ("cpu-train-job", "gpu-train-job"):
        model = trainjob(name)
        expected = model["metadata"]["labels"]
        assert patch_pod(model)["metadata"]["labels"] == expected
        patch = model["spec"]["runtimePatches"][0]["trainingRuntimeSpec"]["template"]
        assert patch["metadata"]["labels"] == expected
        assert patch["spec"]["replicatedJobs"][0]["template"]["metadata"]["labels"] == expected


class FakeAPI:
    def __init__(self, *, workflow=True, condition=None):
        self.objects = {}
        self.calls = []
        self.block_delete = set()
        self.defer_workflow_stop = False
        if workflow:
            self.objects[ops.workflow_path(NAME)] = self.resource(NAME, "workflow", status={"phase": "Running"})
        if condition is not None:
            self.objects[ops.trainjob_path(NAME)] = self.resource(NAME, "trainjob", status={"conditions": condition})

    @staticmethod
    def resource(name, uid, **extra):
        return {"metadata": {"name": name, "uid": uid, "labels": dict(LABELS)}, **extra}

    def request(self, method, path, data=None):
        self.calls.append((method, path, copy.deepcopy(data)))
        if method == "GET":
            if "?" in path:
                prefix = path.split("?")[0] + "/"
                return {"items": [copy.deepcopy(v) for k, v in self.objects.items() if k.startswith(prefix)]}
            return copy.deepcopy(self.objects.get(path))
        if method == "POST":
            key = path + "/" + data["metadata"]["name"]
            if key in self.objects:
                return None
            self.objects[key] = copy.deepcopy(data)
            self.objects[key]["metadata"]["uid"] = "tombstone"
            return copy.deepcopy(self.objects[key])
        if method == "PATCH":
            obj = self.objects[path]
            obj["metadata"].setdefault("annotations", {}).update(data.get("metadata", {}).get("annotations", {}))
            if data.get("spec", {}).get("shutdown") and not self.defer_workflow_stop:
                obj["status"] = {"phase": "Failed"}
            return copy.deepcopy(obj)
        if method == "DELETE":
            assert data["preconditions"]["uid"] == self.objects[path]["metadata"]["uid"]
            assert data["propagationPolicy"] == "Foreground"
            if path not in self.block_delete:
                del self.objects[path]
            return {}
        raise AssertionError(method)


@pytest.mark.validate
@pytest.mark.parametrize("conditions,state", [([], None), ([{"type": "Complete", "status": "False"}], None),
    ([{"type": "Suspended", "status": "False"}, {"type": "Complete", "status": "True"}], "completed"),
    ([{"type": "Failed", "status": "True", "reason": "DeadlineExceeded"}], "failed")])
def validate_trainjob_conditions(conditions, state):
    assert ops.training_condition({"status": {"conditions": conditions}}) == state


@pytest.mark.validate
def validate_wait_retries_and_checks_conditions_by_name():
    api = FakeAPI(condition=[])
    sleeps = []
    def advance(seconds):
        sleeps.append(seconds)
        api.objects[ops.trainjob_path(NAME)]["status"] = {"conditions": [{"type": "Complete", "status": "True"}]}
    ops.wait_training(api, PAYLOAD, sleep=advance)
    assert sleeps == [5]
    api.objects[ops.trainjob_path(NAME)]["metadata"]["labels"]["mlops-paas.io/tenant-id"] = "other"
    with pytest.raises(ValueError, match="ownership"):
        ops.wait_training(api, PAYLOAD, sleep=advance)


@pytest.mark.validate
@pytest.mark.parametrize("error", [RuntimeError("Kubernetes operation failed (503)."), OSError("Connection unavailable.")])
def validate_wait_handles_api_failure_and_trainjob_failure(error):
    api = FakeAPI(condition=[{"type": "Complete", "status": "True"}])
    original = api.request
    attempts = []
    def temporarily_unavailable(*args):
        attempts.append(args)
        if len(attempts) == 1:
            raise error
        return original(*args)
    api.request = temporarily_unavailable
    sleeps = []
    ops.wait_training(api, PAYLOAD, sleep=sleeps.append)
    assert sleeps == [5]
    api = FakeAPI(condition=[{"type": "Failed", "status": "True"}])
    with pytest.raises(RuntimeError, match="TrainJob failed"):
        ops.wait_training(api, PAYLOAD, sleep=sleeps.append)


@pytest.mark.validate
def validate_cleanup_preserves_timing_until_all_children_are_gone():
    api = FakeAPI(condition=[])
    pod_path = f"/api/v1/namespaces/{ops.TRAINING_NS}/pods/worker"
    pod = api.resource("worker", "pod", status={"containerStatuses": [
        {"name": "prepare-input", "state": {"terminated": {"startedAt": "2026-01-01T00:00:00Z"}}},
        {"name": "node", "state": {"terminated": {"startedAt": "2026-01-01T00:01:00Z", "finishedAt": "2026-01-01T00:02:00Z"}}}]})
    api.objects[pod_path] = pod
    child_path = f"/apis/jobset.x-k8s.io/v1alpha2/namespaces/{ops.TRAINING_NS}/jobsets/{NAME}"
    api.objects[child_path] = api.resource(NAME, "jobset")
    api.block_delete.add(child_path)
    observation = ops.reconcile(api, {**PAYLOAD, "stop": True})
    assert observation["status"] == "error"
    assert observation["started_at"] == "2026-01-01T00:01:00Z"
    assert observation["finished_at"] == "2026-01-01T00:02:00Z"
    api.block_delete.clear()
    # A fresh reconcile after GC/worker restart recovers the same timestamps from the Workflow.
    observation = ops.reconcile(api, {**PAYLOAD, "stop": True})
    assert observation["status"] == "stopped" and observation["finished_at"] == "2026-01-01T00:02:00Z"


@pytest.mark.validate
def validate_cancel_before_submit_is_idempotent_and_blocks_late_events():
    api = FakeAPI(workflow=False)
    first = ops.reconcile(api, {**PAYLOAD, "stop": True})
    assert first["status"] == "stopped" and first["never_started"]
    assert ops.reconcile(api, {**PAYLOAD, "stop": True})["never_started"]
    ops.submit(api, PAYLOAD, "training")
    assert api.objects[ops.workflow_path(NAME)]["spec"]["shutdown"] == "Terminate"


@pytest.mark.validate
def validate_unobserved_workflow_is_not_reported_stopped():
    api = FakeAPI()
    api.objects[ops.workflow_path(NAME)]["status"] = {}
    api.defer_workflow_stop = True
    assert ops.reconcile(api, {**PAYLOAD, "stop": True})["status"] == "error"
    api.defer_workflow_stop = False
    assert ops.reconcile(api, {**PAYLOAD, "stop": True})["status"] == "stopped"


@pytest.mark.validate
def validate_cleanup_refuses_foreign_children_before_any_deletion():
    api = FakeAPI(condition=[])
    path = f"/apis/batch/v1/namespaces/{ops.TRAINING_NS}/jobs/foreign"
    api.objects[path] = api.resource("foreign", "foreign")
    api.objects[path]["metadata"]["labels"]["mlops-paas.io/tenant-id"] = "other"
    with pytest.raises(ValueError, match="ownership"):
        ops.reconcile(api, {**PAYLOAD, "stop": True})
    assert not any(method == "DELETE" for method, _, _ in api.calls)
