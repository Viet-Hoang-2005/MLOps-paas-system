"""Scoped Argo submit/reconcile operations. Runs only in trusted workflow Pods."""

import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
EXECUTION_NS = "mlops-paas-execution"
TRAINING_NS = "mlops-paas-training"
SERVING_NS = "mlops-paas-serving"
TRAINER_API = "trainer.kubeflow.org/v1alpha1"
TRAINING_CONTAINER = "node"
# A tombstone is only a terminated Workflow without Pods. It must outlive any
# replay of the original submit event, otherwise the event recreates the job.
TOMBSTONE_TTL_SECONDS = 7 * 24 * 3600


class Kubernetes:
    def __init__(self):
        root = Path("/var/run/secrets/kubernetes.io/serviceaccount")
        self.token = (root / "token").read_text().strip()
        self.context = ssl.create_default_context(cafile=str(root / "ca.crt"))
        self.url = "https://kubernetes.default.svc"

    def request(self, method, path, data=None):
        request = urllib.request.Request(self.url + path, method=method,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/merge-patch+json" if method == "PATCH" else "application/json"})
        try:
            with urllib.request.urlopen(request, context=self.context, timeout=5) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404 or (method == "POST" and exc.code == 409):
                return None
            raise RuntimeError(f"Kubernetes operation failed ({exc.code}).") from None


def workflow_path(name=""):
    return f"/apis/argoproj.io/v1alpha1/namespaces/{EXECUTION_NS}/workflows" + (f"/{name}" if name else "")


def identity(payload, kind):
    id_field = {"build": "build_id", "deployment": "deployment_id"}.get(kind, "job_id")
    resource_id = payload.get("resource_id", payload.get(id_field, ""))
    resource_label = {"build": "build", "training": "training-job", "drift": "drift-run", "deployment": "deployment"}.get(kind)
    if not resource_label or not re.fullmatch(UUID, resource_id):
        raise ValueError("Invalid execution identity.")
    if not (re.fullmatch(UUID, payload["project_id"]) or (kind == "training" and payload["project_id"] == "")) or not re.fullmatch("T-" + UUID, payload["tenant_id"]):
        raise ValueError("Invalid ownership identity.")
    labels = {
        "mlops-paas.io/tenant-id": payload["tenant_id"],
        "mlops-paas.io/project-id": payload["project_id"],
        f"mlops-paas.io/{resource_label}-id": resource_id,
    }
    prefix = "deploy" if kind == "deployment" else kind
    return f"{prefix}-{resource_id}", labels


def verify(resource, labels):
    actual = resource.get("metadata", {}).get("labels", {})
    if any(actual.get(key) != value for key, value in labels.items()):
        raise ValueError("Execution ownership mismatch.")


def runtime_times(pods, kind):
    started, finished = [], []
    for pod in pods:
        for container in pod.get("status", {}).get("containerStatuses", []):
            if container.get("name") != (TRAINING_CONTAINER if kind == "training" else "main"):
                continue
            state = container.get("state", {})
            timestamp = state.get("running", state.get("terminated", {})).get("startedAt")
            if timestamp:
                started.append(timestamp)
            end = state.get("terminated", {}).get("finishedAt")
            if end:
                finished.append(end)
    result = {"started_at": min(started)} if started else {}
    if finished:
        result["finished_at"] = max(finished)
    return result


def submit(api, payload, kind):
    name, labels = identity(payload, kind)
    existing = api.request("GET", workflow_path(name))
    if existing:
        verify(existing, labels)
        return existing
    template = {
        "build": "mlops-paas-model-packager-template",
        "training": "mlops-paas-training-pipeline-template",
        "drift": "mlops-paas-evidently-template",
        "deployment": "mlops-paas-model-server-deploy-template",
    }[kind]
    workflow = {
        "apiVersion": "argoproj.io/v1alpha1", "kind": "Workflow",
        "metadata": {"name": name, "namespace": EXECUTION_NS, "labels": labels},
        "spec": {"workflowTemplateRef": {"name": template},
            "arguments": {"parameters": [{"name": key, "value": str(value)} for key, value in payload.items()]}},
    }
    if kind in {"training", "drift"}:
        workflow["spec"]["activeDeadlineSeconds"] = (
            int(payload.get("max_runtime_seconds", 3600)) + int(payload.get("dispatch_timeout_seconds", 1800)) + 60
        )
    created = api.request("POST", workflow_path(), workflow)
    if created is None:
        created = api.request("GET", workflow_path(name))
    if not created:
        raise RuntimeError("Workflow creation remains unconfirmed.")
    verify(created, labels)
    return created


def trainjob_path(name):
    return f"/apis/{TRAINER_API}/namespaces/{TRAINING_NS}/trainjobs/{name}"


def training_condition(job):
    conditions = (job or {}).get("status", {}).get("conditions", [])
    if any(c.get("type") == "Failed" and str(c.get("status")).lower() == "true" for c in conditions):
        return "failed"
    if any(c.get("type") == "Complete" and str(c.get("status")).lower() == "true" for c in conditions):
        return "completed"
    return None


def wait_training(api, payload, *, sleep=time.sleep):
    name, labels = identity(payload, "training")
    while True:
        try:
            job = api.request("GET", trainjob_path(name))
        except (RuntimeError, OSError):
            sleep(5)
            continue
        if not job:
            raise RuntimeError("Training workload disappeared before completion.")
        verify(job, labels)
        state = training_condition(job)
        if state == "completed":
            return
        if state == "failed":
            raise RuntimeError("TrainJob failed.")
        sleep(5)


def _owned_list(api, path, selector, labels):
    resources = api.request("GET", f"{path}?{selector}")["items"]
    for resource in resources:
        verify(resource, labels)
    return resources


def _delete_owned(api, path, resource):
    uid = resource["metadata"]["uid"]
    api.request("DELETE", path, {"preconditions": {"uid": uid}, "propagationPolicy": "Foreground"})


def reconcile_build_stop(api, name, labels):
    path = workflow_path(name)
    workflow = api.request("GET", path)
    if not workflow:
        api.request("POST", workflow_path(), {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Workflow",
            "metadata": {"name": name, "namespace": EXECUTION_NS, "labels": labels},
            "spec": {
                "shutdown": "Terminate",
                "workflowTemplateRef": {"name": "mlops-paas-job-tombstone-template"},
                "ttlStrategy": {"secondsAfterCompletion": TOMBSTONE_TTL_SECONDS},
            },
        })
        workflow = api.request("GET", path)
    if not workflow:
        raise RuntimeError("Build stop fence is not visible.")
    verify(workflow, labels)

    # Older producers used generateName. Include any of those owned workflows too.
    selector = urllib.parse.urlencode({"labelSelector": ",".join(f"{k}={v}" for k, v in labels.items())})
    workflows = {item["metadata"]["name"]: item for item in _owned_list(api, workflow_path(), selector, labels)}
    workflows[name] = workflow
    waiting = False
    for workflow_name, item in workflows.items():
        spec = item["spec"]
        tombstone = spec.get("workflowTemplateRef", {}).get("name") == "mlops-paas-job-tombstone-template"
        if tombstone and spec.get("shutdown") == "Terminate":
            continue
        if item.get("status", {}).get("phase") not in {"Succeeded", "Failed", "Error"}:
            if spec.get("shutdown") != "Terminate":
                api.request("PATCH", workflow_path(workflow_name), {"spec": {"shutdown": "Terminate"}})
            waiting = True
    # Historical Build pods only have the Build label. This read-only check also
    # covers pods whose workflow reached terminal before their containers exited.
    build_selector = urllib.parse.urlencode({"labelSelector": f"mlops-paas.io/build-id={labels['mlops-paas.io/build-id']}"})
    pods_path = f"/api/v1/namespaces/{EXECUTION_NS}/pods"
    pods = api.request("GET", f"{pods_path}?{build_selector}")["items"]
    if waiting or any(pod.get("status", {}).get("phase") not in {"Succeeded", "Failed"} for pod in pods):
        return {"status": "error", "error": "Build runtime cleanup is pending."}
    return {"status": "stopped"}


def reconcile(api, payload):
    kind = payload["kind"]
    name, labels = identity(payload, kind)
    if kind == "build" and payload.get("stop") is True:
        return reconcile_build_stop(api, name, labels)
    workflow = api.request("GET", workflow_path(name))
    if workflow:
        verify(workflow, labels)
    selector = urllib.parse.urlencode({"labelSelector": ",".join(f"{key}={value}" for key, value in labels.items())})
    if kind == "build" and not workflow:
        owned_workflows = _owned_list(api, workflow_path(), selector, labels)
        if owned_workflows:
            workflow = owned_workflows[-1]
    workload_path = trainjob_path(name)
    job = api.request("GET", workload_path) if kind == "training" else None
    if job:
        verify(job, labels)
    pod_ns = TRAINING_NS if kind == "training" else EXECUTION_NS
    pods_path = f"/api/v1/namespaces/{pod_ns}/pods"
    pods = _owned_list(api, pods_path, selector, labels)
    if kind == "build" and not pods:
        build_selector = urllib.parse.urlencode({"labelSelector": f"mlops-paas.io/build-id={labels['mlops-paas.io/build-id']}"})
        pods = api.request("GET", f"{pods_path}?{build_selector}")["items"]
    result = runtime_times(pods, kind)
    # Preserve trusted pod timing across foreground GC, worker restarts and repeated cancellation.
    annotations = (workflow or {}).get("metadata", {}).get("annotations", {})
    for key in ("started_at", "finished_at"):
        if key not in result and annotations.get(f"mlops-paas.io/{key}"):
            result[key] = annotations[f"mlops-paas.io/{key}"]
    children = []
    if kind == "training":
        for group, resource in (("jobset.x-k8s.io/v1alpha2", "jobsets"), ("batch/v1", "jobs")):
            path = f"/apis/{group}/namespaces/{TRAINING_NS}/{resource}"
            children.append((path, _owned_list(api, path, selector, labels)))
    serving_pods_path = f"/api/v1/namespaces/{SERVING_NS}/pods"
    serving_paths = (
        f"/api/v1/namespaces/{SERVING_NS}/services/{name}-svc",
        f"/apis/apps/v1/namespaces/{SERVING_NS}/deployments/{name}",
    ) if kind == "deployment" else ()
    if workflow and result:
        api.request("PATCH", workflow_path(name), {"metadata": {"annotations": {
            f"mlops-paas.io/{key}": value for key, value in result.items()
        }}})
    if payload.get("stop"):
        never_started = annotations.get("mlops-paas.io/never-started") == "true"
        if not workflow:
            # A tombstone prevents an already-delivered submit event from recreating work.
            tombstone = {"apiVersion": "argoproj.io/v1alpha1", "kind": "Workflow",
                "metadata": {"name": name, "namespace": EXECUTION_NS, "labels": labels},
                "spec": {"shutdown": "Terminate", "workflowTemplateRef": {"name": "mlops-paas-job-tombstone-template"},
                         "ttlStrategy": {"secondsAfterCompletion": TOMBSTONE_TTL_SECONDS}, "podGC": {"strategy": "OnPodCompletion"}}}
            created = api.request("POST", workflow_path(), tombstone)
            workflow = api.request("GET", workflow_path(name))
            verify(workflow, labels)
            # Only a newly created tombstone proves that no submit ever won this name.
            never_started = bool(created and not job and not pods and not any(items for _, items in children))
            if never_started:
                api.request("PATCH", workflow_path(name), {"metadata": {"annotations": {"mlops-paas.io/never-started": "true"}}})
        stop_spec = {"shutdown": "Terminate"}
        if kind != "training":
            stop_spec["ttlStrategy"] = {
                "secondsAfterCompletion": TOMBSTONE_TTL_SECONDS,
                "secondsAfterSuccess": TOMBSTONE_TTL_SECONDS,
                "secondsAfterFailure": TOMBSTONE_TTL_SECONDS,
            }
        for attempt in range(3):
            try:
                api.request("PATCH", workflow_path(name), {"spec": stop_spec})
                break
            except RuntimeError as exc:
                if attempt == 2 or "409" not in str(exc):
                    raise
                workflow = api.request("GET", workflow_path(name))
                if not workflow:
                    break
        if result:
            api.request("PATCH", workflow_path(name), {"metadata": {"annotations": {
                f"mlops-paas.io/{key}": value for key, value in result.items()
            }}})
        if job:
            _delete_owned(api, workload_path, job)
        for path, resources in children:
            for child in resources:
                _delete_owned(api, f"{path}/{child['metadata']['name']}", child)
        for pod in pods:
            _delete_owned(api, f"{pods_path}/{pod['metadata']['name']}", pod)
        for path in serving_paths:
            resource = api.request("GET", path)
            if resource:
                verify(resource, labels)
                _delete_owned(api, path, resource)
        remaining = _owned_list(api, pods_path, selector, labels)
        remaining_children = any(_owned_list(api, path, selector, labels) for path, _ in children)
        remaining_job = api.request("GET", workload_path) if kind == "training" else None
        if remaining_job:
            verify(remaining_job, labels)
        workflow = api.request("GET", workflow_path(name))
        if workflow:
            verify(workflow, labels)
        phase = (workflow or {}).get("status", {}).get("phase")
        never_started = never_started and not result.get("started_at")
        # A Workflow with no observed phase can still have an in-flight resource step.
        # Only our never-started tombstone may be considered stopped before a terminal phase.
        terminating = not workflow or (
            phase not in {"Succeeded", "Failed", "Error"} and not never_started
        )
        serving_remaining = serving_paths and (
            any(api.request("GET", path) for path in serving_paths)
            or _owned_list(api, serving_pods_path, selector, labels)
        )
        if remaining or remaining_job or remaining_children or terminating or serving_remaining:
            return {**result, "status": "error", "error": "Runtime cleanup is pending."}
        # If the workflow reached a terminal phase and all runtime resources are gone
        # without ever recording a container start time, the runtime never started.
        never_started = (never_started or phase in {"Succeeded", "Failed", "Error"}) and not result.get("started_at")
        return {**result, "status": "stopped", "never_started": never_started}
    condition = training_condition(job)
    phase = (workflow or {}).get("status", {}).get("phase")
    if condition == "failed":
        return {**result, "status": "failed", "error": "TrainJob failed."}
    if kind == "deployment":
        service, dep = (api.request("GET", path) for path in serving_paths)
        for resource in (service, dep):
            if resource:
                verify(resource, labels)
        rollout = (dep or {}).get("status", {})
        generation = (dep or {}).get("metadata", {}).get("generation", 1)
        if service and rollout.get("observedGeneration", 0) >= generation and rollout.get("availableReplicas", 0) >= 1:
            return {**result, "status": "completed"}
        if phase not in {"Failed", "Error"}:
            return {**result, "status": "running" if (workflow or dep or service) else "not_found"}
    if phase in {"Failed", "Error"}:
        return {**result, "status": "failed", "error": "Argo workload failed."}
    if condition == "completed" or (kind != "training" and phase == "Succeeded"):
        return {**result, "status": "completed"}
    return {**result, "status": "running" if (workflow or job or (kind == "build" and pods)) else "not_found"}


def main():
    payload = json.loads(os.environ["EXECUTION_PAYLOAD"])
    api = Kubernetes()
    if sys.argv[1] == "wait-training":
        wait_training(api, payload)
        return
    if sys.argv[1] == "submit":
        submit(api, payload, os.environ["EXECUTION_KIND"])
        return
    _name, _ = identity(payload, payload["kind"])
    url = urllib.parse.urlsplit(payload["callback_url"])
    prefix = f"/internal/executions/{payload['kind']}/{payload['resource_id']}/"
    stop_callback = url.path == f"{prefix}stops/" and payload.get("stop") is True and payload["kind"] in {
        "build", "deployment", "drift"
    }
    expected_path = f"{prefix}{'stops' if stop_callback else 'observations'}/"
    if url.scheme != "http" or url.netloc not in {"mlops-paas-control-plane:8000", "mlops-paas-control-plane.mlops-paas-core.svc.cluster.local:8000"} or url.path != expected_path or url.query:
        raise ValueError("Invalid observation callback destination.")
    try:
        observation = reconcile(api, payload)
        if stop_callback:
            deadline = time.monotonic() + 120
            while observation["status"] != "stopped" and time.monotonic() < deadline:
                time.sleep(2)
                observation = reconcile(api, payload)
    except (RuntimeError, ValueError, KeyError, TypeError, OSError):
        observation = {"status": "error", "error": "Argo observation unavailable."}
    request = urllib.request.Request(payload["callback_url"], method="POST", data=json.dumps(observation).encode(),
        headers={"Authorization": f"Bearer {payload['callback_token']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=20 if payload["kind"] in {"build", "deployment"} and not stop_callback else 5) as response:
        response.read()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError, TypeError, OSError):
        print("Execution operation unavailable.", file=sys.stderr)
        sys.exit(1)
