import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml


spec = importlib.util.spec_from_file_location("job_ops", Path(__file__).parents[2] / "argo/scripts/job_ops.py")
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)
ID = "00000000-0000-0000-0000-000000000001"
PROJECT = "00000000-0000-0000-0000-000000000002"
TENANT = "T-00000000-0000-0000-0000-000000000003"


@pytest.fixture
def payload():
    return {"job_id": ID, "resource_id": ID, "project_id": PROJECT, "tenant_id": TENANT, "kind": "training", "job_name": f"training-{ID}", "max_runtime_seconds": 43200, "dispatch_timeout_seconds": 1800}


def workflow(payload, phase="Running"):
    name, labels = ops.identity(payload, payload["kind"])
    return {"metadata": {"name": name, "labels": labels, "uid": ID, "resourceVersion": "1"}, "status": {"phase": phase}}


def test_duplicate_submit_adopts_owned_workflow(payload):
    existing = workflow(payload)
    api = Mock()
    api.request.return_value = existing
    assert ops.submit(api, payload, "training") is existing
    api.request.assert_called_once_with("GET", ops.workflow_path(f"training-{ID}"))


def test_create_conflict_rechecks_ownership(payload):
    api = Mock()
    existing = workflow(payload)
    api.request.side_effect = [None, None, existing]
    assert ops.submit(api, payload, "training") == existing
    created = api.request.call_args_list[1].args[2]
    assert created["metadata"]["name"] == f"training-{ID}"
    assert created["spec"]["activeDeadlineSeconds"] == 45060
    assert {p["name"]: p["value"] for p in created["spec"]["arguments"]["parameters"]}["max_runtime_seconds"] == "43200"


def test_wrong_ownership_never_adopted(payload):
    api = Mock()
    api.request.return_value = {"metadata": {"labels": {}}}
    with pytest.raises(ValueError, match="ownership"):
        ops.submit(api, payload, "training")
    assert api.request.call_count == 1


def test_stop_before_dispatch_creates_tombstone(payload):
    payload["stop"] = True
    stored = None

    def request(method, path, data=None):
        nonlocal stored
        if "/pods" in path:
            return {"items": []}
        if "/pytorchjobs/" in path:
            return None
        if method == "POST":
            stored = data
            stored["metadata"].update(uid=ID, resourceVersion="1")
        return stored

    api = Mock()
    api.request.side_effect = request
    assert ops.reconcile(api, payload)["status"] == "stopped"
    assert stored["spec"]["shutdown"] == "Terminate"
    assert stored["spec"]["workflowTemplateRef"]["name"] == "mlops-paas-job-tombstone-template"
    assert ops.submit(api, payload, "training") is stored


def test_cleanup_waits_for_terminating_workflow(payload):
    payload["stop"] = True
    api = Mock()
    api.request.side_effect = lambda method, path, data=None: ({"items": []} if "/pods" in path else None if "/pytorchjobs/" in path else workflow(payload))
    assert ops.reconcile(api, payload)["status"] == "error"


@pytest.mark.parametrize("kind,runner", [("training", "pytorch"), ("drift", "main")])
def test_runtime_times_use_runner_not_executor(kind, runner):
    pods = [{"status": {"containerStatuses": [
        {"name": "wait", "state": {"terminated": {"startedAt": "2026-10-07T01:00:00Z", "finishedAt": "2026-10-07T04:00:00Z"}}},
        {"name": runner, "state": {"terminated": {"startedAt": "2026-10-07T02:00:00Z", "finishedAt": "2026-10-07T03:00:00Z"}}},
    ]}}]
    assert ops.runtime_times(pods, kind) == {"started_at": "2026-10-07T02:00:00Z", "finished_at": "2026-10-07T03:00:00Z"}


def test_sensor_forwards_entire_training_payload():
    root = Path(__file__).parents[2]
    sensor = yaml.safe_load((root / "argo/sensor.yaml").read_text())
    triggers = {t["template"]["name"]: t["template"]["k8s"] for t in sensor["spec"]["triggers"]}
    for name, kind in (("train-workflow-trigger", "training"), ("drift-workflow-trigger", "drift")):
        trigger = triggers[name]
        resource = trigger["source"]["resource"]
        assert resource["spec"]["workflowTemplateRef"]["name"] == "mlops-paas-job-submit-template"
        assert resource["spec"]["arguments"]["parameters"][0]["value"] == kind
        assert trigger["parameters"][0]["src"]["dataTemplate"] == "{{ .Input.body | toJson }}"
    training = yaml.safe_load((root / "argo/workflows/training-workflowtemplate.yaml").read_text())
    for template in training["spec"]["templates"]:
        if "resource" in template:
            manifest = template["resource"]["manifest"]
            assert "MAX_RUNTIME_SECONDS" in manifest and "inputs.parameters.max_runtime_seconds" in manifest
            assert "S3_INPUT_DOWNLOAD_CAPABILITY" in manifest
