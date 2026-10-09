import importlib.util
import urllib.parse
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
    # Must outlive the replay of the original submit event (days, not minutes).
    assert stored["spec"]["ttlStrategy"]["secondsAfterCompletion"] >= 7 * 24 * 3600
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


def test_kubernetes_request_error_handling(monkeypatch):
    k8s = ops.Kubernetes.__new__(ops.Kubernetes)
    k8s.token = "fake-token"
    k8s.context = None
    k8s.url = "https://k8s.test"

    import urllib.error

    def mock_urlopen_409(req, *args, **kwargs):
        raise urllib.error.HTTPError(req.full_url, 409, "Conflict", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen_409)

    # POST on 409 returns None (already exists)
    assert k8s.request("POST", "/test", {}) is None

    # PATCH on 409 must NOT return None; it must raise RuntimeError
    with pytest.raises(RuntimeError, match=r"Kubernetes operation failed \(409\)"):
        k8s.request("PATCH", "/test", {})

    # 404 returns None
    def mock_urlopen_404(req, *args, **kwargs):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen_404)
    assert k8s.request("PATCH", "/test", {}) is None
    assert k8s.request("GET", "/test") is None


def test_reconcile_stop_retries_patch_409(payload):
    payload["stop"] = True
    wf = workflow(payload)
    api = Mock()
    patch_calls = 0

    def request(method, path, data=None):
        nonlocal patch_calls
        if "/pods" in path:
            return {"items": []}
        if "/pytorchjobs/" in path:
            return None
        if method == "PATCH":
            patch_calls += 1
            if patch_calls == 1:
                raise RuntimeError("Kubernetes operation failed (409).")
            return wf
        return wf

    api.request.side_effect = request
    res = ops.reconcile(api, payload)
    assert res["status"] == "error"  # phase is Running
    assert patch_calls == 2


def test_reconcile_stop_raises_on_persistent_patch_409(payload):
    payload["stop"] = True
    wf = workflow(payload)
    api = Mock()

    def request(method, path, data=None):
        if "/pods" in path:
            return {"items": []}
        if "/pytorchjobs/" in path:
            return None
        if method == "PATCH":
            raise RuntimeError("Kubernetes operation failed (409).")
        return wf

    api.request.side_effect = request
    with pytest.raises(RuntimeError, match=r"Kubernetes operation failed \(409\)"):
        ops.reconcile(api, payload)


def test_pytorch_jobs_have_owner_reference_and_active_deadline():
    root = Path(__file__).parents[2]
    training = yaml.safe_load((root / "argo/workflows/training-workflowtemplate.yaml").read_text())
    pytorch_templates = [t for t in training["spec"]["templates"] if t.get("name") in {"cpu-pytorch-job", "gpu-pytorch-job"}]
    assert len(pytorch_templates) == 2
    for t in pytorch_templates:
        assert t["resource"]["setOwnerReference"] is True
        manifest = t["resource"]["manifest"]
        assert "kind: PyTorchJob" in manifest
        assert "cleanPodPolicy: Running" in manifest
        assert "activeDeadlineSeconds: {{=asInt(inputs.parameters.max_runtime_seconds)}}" in manifest


def test_operational_workflows_have_ttl_and_pod_gc():
    root = Path(__file__).parents[2]
    job_ops_docs = list(yaml.safe_load_all((root / "argo/workflows/job-operations-workflowtemplate.yaml").read_text()))
    expected_image = "python:3.10-slim@sha256:fd76ade0c607f27677bc04be3c60749f400eedc941d9e72967e19a4cedff80c2"
    for doc in job_ops_docs:
        assert doc["spec"]["ttlStrategy"]["secondsAfterCompletion"] == 300
        assert doc["spec"]["podGC"]["strategy"] == "OnPodCompletion"
        for t in doc["spec"]["templates"]:
            if "container" in t:
                assert t["container"]["image"] == expected_image
        if doc["metadata"]["name"] == "mlops-paas-job-submit-template":
            assert doc["spec"]["activeDeadlineSeconds"] >= 240
            submit_tpl = next(t for t in doc["spec"]["templates"] if t["name"] == "submit")
            assert submit_tpl["retryStrategy"]["limit"] == "3"

    cancel_doc = yaml.safe_load((root / "argo/workflows/training-cancel-workflowtemplate.yaml").read_text())
    assert cancel_doc["spec"]["ttlStrategy"]["secondsAfterCompletion"] == 300
    assert cancel_doc["spec"]["podGC"]["strategy"] == "OnPodCompletion"

    delete_doc = yaml.safe_load((root / "argo/workflows/delete-workflowtemplate.yaml").read_text())
    assert delete_doc["spec"]["ttlStrategy"]["secondsAfterCompletion"] == 300
    assert delete_doc["spec"]["podGC"]["strategy"] == "OnPodCompletion"

    sensor = yaml.safe_load((root / "argo/sensor.yaml").read_text())
    op_triggers = ["cancel-build-workflow-trigger", "drift-workflow-trigger", "delete-workflow-trigger", "train-workflow-trigger", "cancel-train-workflow-trigger", "reconcile-job-trigger"]
    for t in sensor["spec"]["triggers"]:
        if t["template"]["name"] in op_triggers:
            wf_spec = t["template"]["k8s"]["source"]["resource"]["spec"]
            assert wf_spec["ttlStrategy"]["secondsAfterCompletion"] == 300
            assert wf_spec["podGC"]["strategy"] == "OnPodCompletion"



BUILD_ID = "00000000-0000-0000-0000-000000000004"


def build_payload():
    return {"build_id": BUILD_ID, "project_id": PROJECT, "tenant_id": TENANT}


def build_workflow(phase="Running", name="build-model-job-abc"):
    labels = {"mlops.io/tenant-id": TENANT, "mlops.io/project-id": PROJECT, "mlops.io/build-id": BUILD_ID}
    return {"metadata": {"name": name, "labels": labels}, "status": {"phase": phase}}


def test_cancel_build_terminates_only_running_owned_workflows():
    api = Mock()
    api.request.side_effect = [
        {"items": [build_workflow(), build_workflow("Succeeded", "build-model-job-done")]},
        None,
    ]
    ops.cancel_build(api, build_payload())
    listing = api.request.call_args_list[0]
    assert listing.args[0] == "GET"
    for label in (f"mlops.io/build-id={BUILD_ID}", f"mlops.io/project-id={PROJECT}"):
        assert urllib.parse.quote(label, safe="") in listing.args[1]
    patches = [call for call in api.request.call_args_list if call.args[0] == "PATCH"]
    assert [call.args[1] for call in patches] == [ops.workflow_path("build-model-job-abc")]
    assert patches[0].args[2] == {"spec": {"shutdown": "Terminate"}}


def test_cancel_build_refuses_foreign_workflow_and_bad_identity():
    foreign = build_workflow()
    foreign["metadata"]["labels"]["mlops.io/project-id"] = "00000000-0000-0000-0000-0000000000ff"
    api = Mock()
    api.request.return_value = {"items": [foreign]}
    with pytest.raises(ValueError, match="ownership"):
        ops.cancel_build(api, build_payload())
    assert all(call.args[0] != "PATCH" for call in api.request.call_args_list)
    with pytest.raises(ValueError, match="identity"):
        ops.cancel_build(api, {**build_payload(), "build_id": "../x"})


def test_build_template_labels_workflow_and_keeps_callback_secret_away_from_user_code():
    root = Path(__file__).parents[3] / "k8s/argo"
    template = yaml.safe_load((root / "workflows/build-workflowtemplate.yaml").read_text(encoding="utf-8"))
    labels = template["spec"]["workflowMetadata"]["labelsFrom"]
    assert set(labels) == {"mlops.io/build-id", "mlops.io/project-id", "mlops.io/tenant-id"}
    steps = {item["name"]: item for item in template["spec"]["templates"]}
    prepare_env = {item["name"] for item in steps["prepare-package"]["container"]["env"]}
    assert "CONTROL_PLANE_WEBHOOK_SECRET" not in prepare_env
    assert "CONTROL_PLANE_WEBHOOK_SECRET" in {item["name"] for item in steps["notify-success"]["container"]["env"]}
    sensor = yaml.safe_load((root / "sensor.yaml").read_text(encoding="utf-8"))
    assert "cancel-build-dep" in {dep["name"] for dep in sensor["spec"]["dependencies"]}
    source = yaml.safe_load((root / "eventsource.yaml").read_text(encoding="utf-8"))
    assert "cancel-build" in source["spec"]["webhook"]


def test_push_credential_is_only_mounted_where_no_user_code_runs():
    """build-image runs the user's pip install as root; whatever it mounts, that code can read."""
    root = Path(__file__).parents[3] / "k8s/argo"
    template = yaml.safe_load((root / "workflows/build-workflowtemplate.yaml").read_text(encoding="utf-8"))
    spec = template["spec"]
    templates = {item["name"]: item for item in spec["templates"]}
    secret_of = {volume["name"]: volume["secret"]["secretName"] for volume in spec["volumes"]}

    def secrets_mounted(name):
        container = templates[name]["container"]
        return {secret_of[mount["name"]] for mount in container.get("volumeMounts", []) if mount["name"] in secret_of}

    # Pushing credential: push-image only. The base-image pull secret is optional and pull-only.
    assert secrets_mounted("push-image") == {"harbor-registry-dockerconfig"}
    assert secrets_mounted("build-image") <= {"harbor-base-pull-dockerconfig"}
    assert "harbor-registry-dockerconfig" not in secrets_mounted("build-image")
    assert next(v for v in spec["volumes"] if v["name"] == "harbor-base-pull")["secret"]["optional"] is True
    for name in ("build-image", "prepare-package"):
        env = {item["name"] for item in templates[name]["container"].get("env", [])}
        assert not {"CONTROL_PLANE_WEBHOOK_SECRET", "HARBOR_PASSWORD"} & env

    # build-image must not push; push-image publishes the tarball and records the digest.
    build_args = templates["build-image"]["container"]["args"]
    assert "--no-push" in build_args and "--tar-path=/workspace/image.tar" in build_args
    assert not any(arg.startswith("--digest-file") for arg in build_args)
    push = templates["push-image"]["container"]
    assert "--digestfile=/workspace/image-digest" in push["args"]
    assert "docker-archive:/workspace/image.tar" in push["args"]
    assert any(arg.startswith("docker://{{inputs.parameters.image_repository}}:") for arg in push["args"])

    steps = [group[0]["template"] for group in templates["build-model"]["steps"]]
    assert steps == ["prepare-package", "build-image", "push-image", "notify-success"]
