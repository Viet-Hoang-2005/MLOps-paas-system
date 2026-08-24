from pathlib import PurePosixPath


def _clean(value):
    return str(value).strip().strip("/")


def project_prefix(tenant_id, project_id):
    return f"users/{_clean(tenant_id)}/models/{_clean(project_id)}"


def workspace_prefix(tenant_id, project_id, kind):
    if kind not in {"code", "data"}:
        raise ValueError("Workspace kind must be code or data")
    return f"{project_prefix(tenant_id, project_id)}/{kind}/"


def build_input_prefix(tenant_id, project_id, build_id, kind):
    if kind not in {
        "source_artifact",
        "training_output",
        "label_mapping",
        "metrics",
        "params",
        "model_insights",
        "feature_importance",
        "input_schema",
    }:
        raise ValueError("Unsupported build input kind")
    return f"{project_prefix(tenant_id, project_id)}/builds/{_clean(build_id)}/inputs/{kind}/"


def build_prefix(tenant_id, project_id, build_id):
    return f"{project_prefix(tenant_id, project_id)}/builds/{_clean(build_id)}"


def training_job_prefix(tenant_id, project_id, job_id):
    return f"{project_prefix(tenant_id, project_id)}/training/jobs/{_clean(job_id)}"


def training_input_key(tenant_id, project_id, job_id, kind, relative_path):
    if kind not in {"code", "data"}:
        raise ValueError("Training input kind must be code or data")
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Unsafe relative path")
    return f"{training_job_prefix(tenant_id, project_id, job_id)}/input/{kind}/{path.as_posix()}"


def training_output_prefix(tenant_id, project_id, job_id):
    return f"{training_job_prefix(tenant_id, project_id, job_id)}/output/"


def training_mlflow_prefix(tenant_id, project_id, job_id):
    return f"{training_job_prefix(tenant_id, project_id, job_id)}/mlflow/"


def version_prefix(tenant_id, project_id, version_id):
    return f"{project_prefix(tenant_id, project_id)}/versions/{_clean(version_id)}"


def drift_run_prefix(tenant_id, project_id, monitor_id, run_id):
    return f"{project_prefix(tenant_id, project_id)}/drift/{_clean(monitor_id)}/{_clean(run_id)}/"
