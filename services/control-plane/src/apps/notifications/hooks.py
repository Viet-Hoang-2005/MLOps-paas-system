import logging
from .models import Notification
from .services import create_notification

logger = logging.getLogger(__name__)


def notify_training_result(job):
    """Safely notify project owner of a training job terminal state."""
    try:
        owner = getattr(getattr(job, "project", None), "owner", None)
        if not owner:
            return
        level = (
            Notification.Level.SUCCESS
            if job.status == "completed"
            else Notification.Level.ERROR
            if job.status == "failed"
            else Notification.Level.WARNING
        )
        title = f"Training Job: {job.job_name} ({job.status})"
        message = f"Training workflow for project '{job.project.name}' completed with status '{job.status}'."
        create_notification(
            user=owner,
            type=Notification.Type.TRAINING,
            level=level,
            title=title,
            message=message,
            link=f"/dashboard/projects/{job.project.public_id}/training",
            metadata={
                "job_id": str(job.public_id),
                "status": job.status,
                "project_id": str(job.project.public_id),
            },
        )
    except Exception as exc:
        logger.warning("Failed to dispatch training notification: %s", exc)


def notify_build_result(build):
    """Safely notify project owner of a model packaging build result."""
    try:
        owner = getattr(getattr(build, "project", None), "owner", None)
        if not owner:
            return
        is_success = build.status == "ready"
        level = Notification.Level.SUCCESS if is_success else Notification.Level.ERROR
        title = f"Image Build: {build.project.name} ({build.status})"
        message = (
            f"Container image build for model project '{build.project.name}' completed and is ready for deployment."
            if is_success
            else f"Container image build for model project '{build.project.name}' failed: {build.error_message or 'Build failed'}."
        )
        create_notification(
            user=owner,
            type=Notification.Type.BUILD,
            level=level,
            title=title,
            message=message,
            link=f"/dashboard/projects/{build.project.public_id}/deployment",
            metadata={
                "build_id": str(build.public_id),
                "status": build.status,
                "project_id": str(build.project.public_id),
            },
        )
    except Exception as exc:
        logger.warning("Failed to dispatch build notification: %s", exc)


def notify_deployment_result(deployment):
    """Safely notify project owner of a model deployment status change."""
    try:
        owner = getattr(getattr(getattr(deployment, "version", None), "project", None), "owner", None)
        if not owner:
            return
        is_success = deployment.status == "succeeded"
        level = Notification.Level.SUCCESS if is_success else Notification.Level.ERROR
        project = deployment.version.project
        title = f"Endpoint Deployment: {project.name} ({deployment.status})"
        message = (
            f"Model endpoint '{project.name}' (version {deployment.version.version}) is now online and serving traffic."
            if is_success
            else f"Deployment for model '{project.name}' failed: {deployment.error_message or 'Deployment failed'}."
        )
        create_notification(
            user=owner,
            type=Notification.Type.DEPLOYMENT,
            level=level,
            title=title,
            message=message,
            link=f"/dashboard/projects/{project.public_id}/deployment",
            metadata={
                "deployment_id": str(deployment.public_id),
                "status": deployment.status,
                "project_id": str(project.public_id),
            },
        )
    except Exception as exc:
        logger.warning("Failed to dispatch deployment notification: %s", exc)


def notify_drift_result(run):
    """Safely notify project owner of a data drift evaluation result."""
    try:
        project = getattr(getattr(getattr(run, "monitor", None), "version", None), "project", None)
        owner = getattr(project, "owner", None)
        if not owner:
            return
        if run.has_drift:
            title = f"Data Drift Alert: {project.name}"
            message = f"Data drift detected for model '{project.name}' (drift score: {run.drift_score}). Consider reviewing drift metrics and retraining."
            level = Notification.Level.WARNING
        elif run.status == "completed":
            title = f"Data Drift Check: {project.name} (Normal)"
            message = f"Data distribution analysis for model '{project.name}' completed with no significant drift detected."
            level = Notification.Level.INFO
        else:
            return
        create_notification(
            user=owner,
            type=Notification.Type.DRIFT,
            level=level,
            title=title,
            message=message,
            link=f"/dashboard/projects/{project.public_id}/monitoring",
            metadata={
                "run_id": str(run.public_id),
                "has_drift": run.has_drift,
                "score": run.drift_score,
                "project_id": str(project.public_id),
            },
        )
    except Exception as exc:
        logger.warning("Failed to dispatch drift notification: %s", exc)


def notify_project_created(project):
    """Safely notify user that a new model project was created."""
    try:
        owner = getattr(project, "owner", None)
        if not owner:
            return
        create_notification(
            user=owner,
            type=Notification.Type.PROJECT,
            level=Notification.Level.SUCCESS,
            title=f"Model Project Created: {project.name}",
            message=f"Model project '{project.name}' has been created successfully.",
            link="/dashboard/projects",
            metadata={"project_id": str(project.public_id), "action": "created"},
        )
    except Exception as exc:
        logger.warning("Failed to dispatch project created notification: %s", exc)


def notify_project_metadata_updated(project):
    """Safely notify user that model project metadata was updated."""
    try:
        owner = getattr(project, "owner", None)
        if not owner:
            return
        create_notification(
            user=owner,
            type=Notification.Type.PROJECT,
            level=Notification.Level.INFO,
            title=f"Project Metadata Updated: {project.name}",
            message=f"Metadata for model project '{project.name}' (Name, Description, Access mode) has been updated.",
            link="/dashboard/projects",
            metadata={"project_id": str(project.public_id), "action": "metadata_updated"},
        )
    except Exception as exc:
        logger.warning("Failed to dispatch project metadata updated notification: %s", exc)


def notify_project_preview_updated(project):
    """Safely notify user that model preview configuration was updated."""
    try:
        owner = getattr(project, "owner", None)
        if not owner:
            return
        create_notification(
            user=owner,
            type=Notification.Type.PROJECT,
            level=Notification.Level.INFO,
            title=f"Model Preview Updated: {project.name}",
            message=f"Model preview configuration for '{project.name}' has been updated.",
            link="/dashboard/projects",
            metadata={"project_id": str(project.public_id), "action": "preview_updated"},
        )
    except Exception as exc:
        logger.warning("Failed to dispatch project preview updated notification: %s", exc)


def notify_project_deleted(project):
    """Safely notify user that a model project deletion was requested."""
    try:
        owner = getattr(project, "owner", None)
        if not owner:
            return
        create_notification(
            user=owner,
            type=Notification.Type.PROJECT,
            level=Notification.Level.WARNING,
            title=f"Model Project Deleted: {project.name}",
            message=f"Model project '{project.name}' has been deleted and its resources are queued for cleanup.",
            link="/dashboard/projects",
            metadata={"project_id": str(project.public_id), "action": "deleted"},
        )
    except Exception as exc:
        logger.warning("Failed to dispatch project deleted notification: %s", exc)
