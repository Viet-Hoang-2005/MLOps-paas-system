from django.core import signing
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone

STOP_TOKEN_SALT = "argo-runtime-stop"


def project_has_unconfirmed_argo_stops(project):
    from apps.deployment.models import Deployment
    from apps.drift.models import DriftRun

    return (
        project.builds.filter(backend="argo", argo_stop_confirmed_at__isnull=True)
        .filter(
            Q(started_at__isnull=False) | Q(execution_deadline_at__isnull=False)
            | Q(execution_completed_at__isnull=False) | Q(status="building")
        )
        .exists()
        or Deployment.objects.filter(
            version__project=project, backend="argo", argo_stop_confirmed_at__isnull=True
        )
        .exclude(status="failed", external_deployment_id="")
        .exists()
        or DriftRun.objects.filter(
            monitor__version__project=project, monitor__backend="argo", argo_stop_confirmed_at__isnull=True
        )
        .exclude(status__in=("completed", "skipped", "failed"), runtime_started_at__isnull=True, external_run_id="")
        .exists()
    )


def stop_identity(resource, kind):
    if kind == "build":
        project = resource.project
    elif kind == "deployment":
        project = resource.version.project
    else:
        project = resource.monitor.version.project
    return {
        "kind": kind,
        "resource_id": str(resource.public_id),
        "project_id": str(project.public_id),
        "tenant_id": project.owner.tenant_id,
    }


def stop_payload(resource, kind, control_plane_url):
    identity = stop_identity(resource, kind)
    return {
        **identity,
        "stop": True,
        "callback_url": f"{control_plane_url}/internal/executions/{kind}/{resource.public_id}/stops/",
        "callback_token": signing.dumps(identity, salt=STOP_TOKEN_SALT),
    }


def confirm_stop(resource, kind):
    values = {"argo_stop_confirmed_at": timezone.now()}
    if kind == "deployment":
        values["stopped_at"] = values["argo_stop_confirmed_at"]
    elif kind == "build":
        values["execution_completed_at"] = Coalesce("execution_completed_at", values["argo_stop_confirmed_at"])
    return type(resource).objects.filter(pk=resource.pk, argo_stop_confirmed_at__isnull=True).update(**values)
