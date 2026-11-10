"""Render platform TrainJob samples for offline schema and contract verification."""
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATH = "k8s/argo/runtimes/training/single-node.yaml"


def runtime():
    return yaml.safe_load((ROOT / RUNTIME_PATH).read_text(encoding="utf-8"))


def runtime_pod():
    return runtime()["spec"]["template"]["spec"]["replicatedJobs"][0]["template"]["spec"]["template"]["spec"]


def trainjob(template_name, model="t4"):
    workflow = next(yaml.safe_load_all((ROOT / "k8s/argo/workflows/training/workflow.yaml").read_text(encoding="utf-8")))
    template = next(t for t in workflow["spec"]["templates"] if t["name"] == template_name)
    values = {p["name"]: p.get("value", "sample") for p in template["inputs"]["parameters"]}
    values.update(job_id="11111111-1111-1111-1111-111111111111", project_id="",
                  tenant_id="T-22222222-2222-2222-2222-222222222222",
                  job_name="training-11111111-1111-1111-1111-111111111111", vcpu="2", memory="4096",
                  max_runtime_seconds="900", dispatch_timeout_seconds="1800", accelerator_count="1",
                  accelerator_model=model, input_contract="workspace", requirements_text="numpy\npandas")

    def substitute(match):
        expression = match.group()[2:-2]
        if expression.startswith("=toJson(inputs.parameters."):
            return json.dumps(values[expression[len("=toJson(inputs.parameters."):-1]])
        if "asInt(" in expression:
            return str(int(values["max_runtime_seconds"]) + int(values["dispatch_timeout_seconds"]) + 60)
        if expression.startswith("=inputs.parameters.accelerator_model"):
            suffix = "2xlarge" if ".2xlarge" in expression else "xlarge"
            return json.dumps({"t4": f"g4dn.{suffix}", "a10g": f"g5.{suffix}"}.get(model, "invalid-gpu-model"))
        if expression.startswith("inputs.parameters."):
            return str(values[expression[len("inputs.parameters."):]])
        raise ValueError(f"Unsupported Argo expression: {expression}")

    return yaml.safe_load(re.sub(r"\{\{.*?\}\}", substitute, template["resource"]["manifest"]))


def patch_pod(job):
    return job["spec"]["runtimePatches"][0]["trainingRuntimeSpec"]["template"]["spec"]["replicatedJobs"][0]["template"]["spec"]["template"]
