"""Scoped Argo submit/reconcile operations. Runs only in trusted workflow Pods."""

import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
EXECUTION_NS = "mlops-execution"
TRAINING_NS = "user-jobs"
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
    resource_id = payload.get("resource_id", payload.get("job_id", ""))
    if kind not in {"training", "drift"} or not re.fullmatch(UUID, resource_id):
        raise ValueError("Invalid execution identity.")
    if not re.fullmatch(UUID, payload["project_id"]) or not re.fullmatch("T-" + UUID, payload["tenant_id"]):
        raise ValueError("Invalid ownership identity.")
    labels = {
        "mlops.io/tenant-id": payload["tenant_id"],
        "mlops.io/project-id": payload["project_id"],
        f"mlops.io/{'training-job' if kind == 'training' else 'drift-run'}-id": resource_id,
    }
    return f"{kind}-{resource_id}", labels


def verify(resource, labels):
    actual = resource.get("metadata", {}).get("labels", {})
    if any(actual.get(key) != value for key, value in labels.items()):
        raise ValueError("Execution ownership mismatch.")


def runtime_times(pods, kind):
    started, finished = [], []
    for pod in pods:
        for container in pod.get("status", {}).get("containerStatuses", []):
            if container.get("name") != ("pytorch" if kind == "training" else "main"):
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
    template = "mlops-paas-training-pipeline-template" if kind == "training" else "mlops-paas-evidently-template"
    workflow = {
        "apiVersion": "argoproj.io/v1alpha1", "kind": "Workflow",
        "metadata": {"name": name, "namespace": EXECUTION_NS, "labels": labels},
        "spec": {"workflowTemplateRef": {"name": template},
            "activeDeadlineSeconds": int(payload.get("max_runtime_seconds", 3600)) + int(payload.get("dispatch_timeout_seconds", 1800)) + 60,
            "arguments": {"parameters": [{"name": key, "value": str(value)} for key, value in payload.items()]}},
    }
    created = api.request("POST", workflow_path(), workflow)
    if created is None:
        created = api.request("GET", workflow_path(name))
    if not created:
        raise RuntimeError("Workflow creation remains unconfirmed.")
    verify(created, labels)
    return created


def cancel_build(api, payload):
    """Terminate the Workflow of one build; ownership comes from labels set at creation."""
    build_id = payload.get("build_id", "")
    if not re.fullmatch(UUID, build_id) or not re.fullmatch(UUID, payload.get("project_id", "")) or not re.fullmatch("T-" + UUID, payload.get("tenant_id", "")):
        raise ValueError("Invalid build identity.")
    labels = {
        "mlops.io/tenant-id": payload["tenant_id"],
        "mlops.io/project-id": payload["project_id"],
        "mlops.io/build-id": build_id,
    }
    selector = urllib.parse.urlencode({"labelSelector": ",".join(f"{key}={value}" for key, value in labels.items())})
    for workflow in (api.request("GET", f"{workflow_path()}?{selector}") or {}).get("items", []):
        verify(workflow, labels)
        if workflow.get("status", {}).get("phase") in {"Succeeded", "Failed", "Error"}:
            continue
        name = workflow["metadata"]["name"]
        for attempt in range(3):
            try:
                api.request("PATCH", workflow_path(name), {"spec": {"shutdown": "Terminate"}})
                break
            except RuntimeError as exc:
                if attempt == 2 or "409" not in str(exc):
                    raise


def reconcile(api, payload):
    kind = payload["kind"]
    name, labels = identity(payload, kind)
    workflow = api.request("GET", workflow_path(name))
    if workflow:
        verify(workflow, labels)
    workload_path = f"/apis/kubeflow.org/v1/namespaces/{TRAINING_NS}/pytorchjobs/{name}"
    job = api.request("GET", workload_path) if kind == "training" else None
    if job:
        verify(job, labels)
    pod_ns = TRAINING_NS if kind == "training" else EXECUTION_NS
    selector = urllib.parse.urlencode({"labelSelector": ",".join(f"{key}={value}" for key, value in labels.items())})
    pods_path = f"/api/v1/namespaces/{pod_ns}/pods"
    pods = api.request("GET", f"{pods_path}?{selector}")["items"]
    for pod in pods:
        verify(pod, labels)
    result = runtime_times(pods, kind)
    if payload.get("stop"):
        if not workflow:
            # A tombstone prevents an already-delivered submit event from recreating work.
            tombstone = {"apiVersion": "argoproj.io/v1alpha1", "kind": "Workflow",
                "metadata": {"name": name, "namespace": EXECUTION_NS, "labels": labels},
                "spec": {"shutdown": "Terminate", "workflowTemplateRef": {"name": "mlops-paas-job-tombstone-template"},
                         "ttlStrategy": {"secondsAfterCompletion": TOMBSTONE_TTL_SECONDS}, "podGC": {"strategy": "OnPodCompletion"}}}
            api.request("POST", workflow_path(), tombstone)
            workflow = api.request("GET", workflow_path(name))
            verify(workflow, labels)
        for attempt in range(3):
            try:
                api.request("PATCH", workflow_path(name), {"spec": {"shutdown": "Terminate"}})
                break
            except RuntimeError as exc:
                if attempt == 2 or "409" not in str(exc):
                    raise
                workflow = api.request("GET", workflow_path(name))
                if not workflow:
                    break
        if job:
            api.request("DELETE", workload_path, {"preconditions": {"uid": job["metadata"]["uid"]}})
        for pod in pods:
            api.request("DELETE", f"{pods_path}/{pod['metadata']['name']}", {"preconditions": {"uid": pod["metadata"]["uid"]}})
        remaining = api.request("GET", f"{pods_path}?{selector}")["items"]
        remaining_job = api.request("GET", workload_path) if kind == "training" else None
        if remaining_job:
            verify(remaining_job, labels)
        workflow = api.request("GET", workflow_path(name))
        if workflow:
            verify(workflow, labels)
        terminating = workflow and workflow.get("status", {}).get("phase") in {"Running", "Pending"}
        return {**result, "status": "error", "error": "Runtime cleanup is pending."} if remaining or remaining_job or terminating else {**result, "status": "stopped"}
    conditions = (job or {}).get("status", {}).get("conditions", [])
    succeeded = any(c["type"] == "Succeeded" and str(c["status"]).lower() == "true" for c in conditions)
    failed = any(c["type"] == "Failed" and str(c["status"]).lower() == "true" for c in conditions)
    phase = (workflow or {}).get("status", {}).get("phase")
    if succeeded or phase == "Succeeded":
        return {**result, "status": "completed"}
    if failed or phase in {"Failed", "Error"}:
        return {**result, "status": "failed", "error": "Argo workload failed."}
    return {**result, "status": "running" if workflow or job else "not_found"}


def main():
    payload = json.loads(os.environ["EXECUTION_PAYLOAD"])
    api = Kubernetes()
    if sys.argv[1] == "submit":
        if os.environ["EXECUTION_KIND"] == "cancel-build":
            cancel_build(api, payload)
        else:
            submit(api, payload, os.environ["EXECUTION_KIND"])
        return
    name, _ = identity(payload, payload["kind"])
    expected_path = f"/internal/executions/{payload['kind']}/{payload['resource_id']}/observations/"
    url = urllib.parse.urlsplit(payload["callback_url"])
    if url.scheme != "http" or url.netloc not in {"mlops-paas-control-plane:8000", "mlops-paas-control-plane.mlops-control-plane.svc.cluster.local:8000"} or url.path != expected_path or url.query:
        raise ValueError("Invalid observation callback destination.")
    try:
        observation = reconcile(api, payload)
    except Exception:
        observation = {"status": "error", "error": "Argo observation unavailable."}
    request = urllib.request.Request(payload["callback_url"], method="POST", data=json.dumps(observation).encode(),
        headers={"Authorization": f"Bearer {payload['callback_token']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        response.read()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Execution operation unavailable.", file=sys.stderr)
        sys.exit(1)
