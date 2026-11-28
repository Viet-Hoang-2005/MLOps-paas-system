import logging

from apps.deployment.models import Build, Deployment
from apps.drift.models import DriftRun
from apps.training.jobs.models import TrainingJob

logger = logging.getLogger(__name__)


TERMINAL = {"completed", "failed", "cancelled", "skipped"}


ARGO_SERVING_KINDS = {"build", "deployment"}


MODELS = {"training": TrainingJob, "drift": DriftRun, "build": Build, "deployment": Deployment}


WATCH_FIELDS = [
    field.name
    for field in TrainingJob._meta.fields
    if field.name
    in {
        "next_execution_check_at",
        "execution_check_token",
        "execution_check_lease_until",
        "dispatch_deadline_at",
        "execution_deadline_at",
        "runtime_started_at",
        "execution_stop_requested",
        "observation_status",
        "observation_error",
        "observation_failures",
    }
]


def model_for(kind):
    if kind not in MODELS:
        raise ValueError("Unsupported execution kind")
    return MODELS[kind]


def resource_for(kind, public_id):
    related = {
        "training": ("project__owner", "owner"),
        "drift": ("monitor__version__project__owner",),
        "build": ("project__owner",),
        "deployment": ("version__project__owner", "endpoint"),
    }
    return model_for(kind).objects.select_related(*related[kind]).filter(public_id=public_id).first()


def project_for(row, kind):
    if kind in {"training", "build"}:
        return row.project
    if kind == "deployment":
        return row.version.project
    return row.monitor.version.project


def ownership_for(row, kind):
    if kind == "training":
        return str(row.owner.tenant_id), row.runtime_project_id
    project = project_for(row, kind)
    return str(project.owner.tenant_id), str(project.public_id)
