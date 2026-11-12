"""Asynchronous, deterministic preparation of an isolated read-only Input volume."""
import docker.errors
from common.api.exceptions import Conflict
from .job_containers import labels_for

IMAGE = "mlops-paas-training-runner:latest"


def names(job):
    return f"training-input-{job.public_id}", f"training-input-{job.public_id}"


def _owned(resource, job):
    resource.reload()
    labels = resource.attrs.get("Labels") or resource.attrs.get("Config", {}).get("Labels") or {}
    expected = {**labels_for(job, "training"), "mlops_role": "input"}
    if any(labels.get(k) != v for k, v in expected.items()):
        raise Conflict("Input runtime ownership mismatch.")
    return resource


def observe(client, job):
    helper_name, _ = names(job)
    try:
        helper = _owned(client.containers.get(helper_name), job)
    except docker.errors.NotFound:
        return {"status": "not_found"}
    state = helper.attrs.get("State", {})
    if state.get("Status") == "created":
        return {"status": "created", "prepared": False}
    if state.get("Status") in {"running", "restarting"}:
        return {"status": "preparing"}
    if state.get("ExitCode") != 0:
        detail = helper.logs(tail=5).decode("utf-8", errors="replace")[-1000:]
        return {"status": "failed", "error": "Training Input preparation failed. " + detail}
    return {"status": "created", "prepared": True}


def prepare(client, job, environment, network):
    helper_name, volume_name = names(job)
    state = observe(client, job)
    if state["status"] == "created":
        if state["prepared"]:
            return True
        _owned(client.containers.get(helper_name), job).start()
        return False
    if state["status"] == "failed":
        raise Conflict(state["error"])
    if state["status"] == "preparing":
        return False
    client.images.get(IMAGE)  # No implicit pull for trusted helper images.
    labels = {**labels_for(job, "training"), "mlops_role": "input"}
    try:
        _owned(client.volumes.get(volume_name), job)
    except docker.errors.NotFound:
        client.volumes.create(name=volume_name, labels=labels)
    try:
        client.containers.run(IMAGE, name=helper_name, command=["python", "-m", "src.prepare"],
            detach=True, remove=False, user="0:0", labels=labels,
            environment={k: environment[k] for k in ("S3_INPUT_DOWNLOAD_URL", "S3_INPUT_DOWNLOAD_CAPABILITY")},
            volumes={volume_name: {"bind": "/prepared", "mode": "rw"}}, network=network,
            nano_cpus=250_000_000, mem_limit="256m", memswap_limit="256m", cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"], read_only=True, tmpfs={"/tmp": "rw,nosuid,nodev,size=16m"})
    except docker.errors.APIError as exc:
        if exc.status_code != 409:
            raise
        _owned(client.containers.get(helper_name), job)
    return False


def cleanup(client, job):
    helper_name, volume_name = names(job)
    try:
        helper = _owned(client.containers.get(helper_name), job)
        helper.remove(force=True)
    except docker.errors.NotFound:
        pass
    try:
        volume = _owned(client.volumes.get(volume_name), job)
        volume.remove()
    except docker.errors.NotFound:
        pass
