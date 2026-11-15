"""Protect Trainer v2 image promotion from stale v1 template edits."""

import pytest
import yaml

from ..trainer import ROOT, runtime


@pytest.mark.validate
def validate_cd_promotes_both_trainer_runtime_containers():
    workflow = yaml.safe_load((ROOT / ".github/workflows/cd.yml").read_text(encoding="utf-8"))
    step = next(
        step
        for step in workflow["jobs"]["gitops-promotion"]["steps"]
        if step.get("name") == "Update Image Tags in Kustomization & WorkflowTemplates"
    )
    script = step["run"]
    assert "cpu-pytorch-job" not in script
    assert "gpu-pytorch-job" not in script
    assert "export TRAINING_RUNNER_IMAGE=" in script
    edits = [line for line in script.splitlines() if "strenv(TRAINING_RUNNER_IMAGE)" in line]
    assert len(edits) == 2
    assert all(line.endswith("k8s/argo/runtimes/training/single-node.yaml") for line in edits)
    assert any(".initContainers[]" in line and 'select(.name == "prepare-input")' in line for line in edits)
    assert any(".containers[]" in line and 'select(.name == "node")' in line for line in edits)
    pod = runtime()["spec"]["template"]["spec"]["replicatedJobs"][0]["template"]["spec"]["template"]["spec"]
    assert pod["initContainers"][0]["image"] == pod["containers"][0]["image"]
