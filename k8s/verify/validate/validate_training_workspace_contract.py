"""Offline contract checks independent of a cluster or a Kustomize executable."""
import importlib.util
from pathlib import Path
import re
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.validate
def validate_training_input_is_a_real_readonly_mount():
    workflow = next(item for item in yaml.safe_load_all((ROOT / "k8s/argo/workflows/training/workflow.yaml").read_text(encoding="utf-8")) if item["metadata"]["name"] == "mlops-paas-training-pipeline-template")
    templates = {template["name"]: template for template in workflow["spec"]["templates"]}
    for name in ("cpu-pytorch-job", "gpu-pytorch-job"):
        raw = templates[name]["resource"]["manifest"]
        job = yaml.safe_load(re.sub(r"\{\{.*?\}\}", "placeholder", raw))
        pod = job["spec"]["pytorchReplicaSpecs"]["Master"]["template"]["spec"]
        assert pod["automountServiceAccountToken"] is False
        assert pod["securityContext"]["runAsNonRoot"] is True
        runner = pod["containers"][0]
        init = pod["initContainers"][0]
        assert init["command"] == ["python", "-m", "src.prepare"]
        assert runner["volumeMounts"] == [{"name": "training-input", "mountPath": "/prepared", "readOnly": True}]
        assert init["volumeMounts"] == [{"name": "training-input", "mountPath": "/prepared"}]
        assert all("hostPath" not in volume for volume in pod["volumes"])
        assert runner["securityContext"]["capabilities"]["drop"] == ["ALL"]
        assert "RUNTIME_CONFIG_CAPABILITY" not in {item["name"] for item in init["env"]}
        assert {item["name"] for item in runner["env"]} >= {"INPUT_CONTRACT", "PREPARED_INPUT_DIR", "RUNTIME_CONFIG_URL", "RUNTIME_CONFIG_CAPABILITY"}


@pytest.mark.validate
def validate_unassigned_training_uses_tenant_and_job_identity():
    spec = importlib.util.spec_from_file_location("job_ops_workspace", ROOT / "k8s/argo/workflows/operations/scripts/job_ops.py")
    operations = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(operations)
    resource = "11111111-1111-1111-1111-111111111111"
    tenant = "T-22222222-2222-2222-2222-222222222222"
    name, labels = operations.identity({"job_id": resource, "project_id": "", "tenant_id": tenant}, "training")
    assert name == "training-" + resource
    assert labels["mlops-paas.io/tenant-id"] == tenant
    with pytest.raises(ValueError):
        operations.identity({"resource_id": resource, "project_id": "", "tenant_id": tenant}, "drift")
    sensor = yaml.safe_load((ROOT / "k8s/argo/events/sensor.yaml").read_text(encoding="utf-8"))
    training = next(item for item in sensor["spec"]["dependencies"] if item["name"] == "train-dep")
    filters = {item["path"]: item for item in training["filters"]["data"]}
    assert re.fullmatch(filters["body.project_id"]["value"][0], "")
    assert not re.fullmatch(filters["body.job_id"]["value"][0], "")
    assert not re.fullmatch(filters["body.tenant_id"]["value"][0], "")
