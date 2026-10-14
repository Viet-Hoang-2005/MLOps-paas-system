import uuid

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ModelProject
from infrastructure.storage.paths import project_prefix
from ..auth import (
    _is_project_allowed_for_api_key,
    _require_auth,
    _scoped_projects_queryset,
)


def _project_mlflow_artifact_uri(project):
    key = f"{project_prefix(project.owner.tenant_id, project.public_id)}/training/jobs"
    return f"mlflow-artifacts:/{key}"


class MLflowExperimentsGetByNameView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get_or_post(self, request):
        job, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        exp_name = request.query_params.get("experiment_name") or request.data.get("experiment_name") or ""
        target_project = project
        if not target_project:
            qs = _scoped_projects_queryset(tenant_id, api_key)
            if exp_name:
                target_project = qs.filter(name=exp_name).first()
            else:
                target_project = qs.first()

        if not target_project:
            if exp_name and api_key is not None and api_key.allowed_projects.exists():
                forbidden = ModelProject.objects.filter(owner__tenant_id=tenant_id, name=exp_name, deletion_state="active").first()
                if forbidden:
                    return Response(
                        {"error_code": "PERMISSION_DENIED", "message": "API key is not authorized for this experiment."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            return Response(
                {"error_code": "RESOURCE_DOES_NOT_EXIST", "message": f"Experiment '{exp_name}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if api_key is not None and not _is_project_allowed_for_api_key(api_key, target_project):
            return Response(
                {"error_code": "PERMISSION_DENIED", "message": "API key is not authorized for this experiment."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {
                "experiment": {
                    "experiment_id": str(target_project.public_id),
                    "name": target_project.name,
                    "artifact_location": _project_mlflow_artifact_uri(target_project),
                    "lifecycle_stage": "active",
                    "tags": [{"key": "tenant_id", "value": tenant_id}],
                }
            }
        )

    def get(self, request):
        return self.get_or_post(request)

    def post(self, request):
        return self.get_or_post(request)


class MLflowExperimentsCreateView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        job, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        if job is not None:
            return Response(
                {"error_code": "PERMISSION_DENIED", "message": "Capability token cannot create new experiments."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if api_key is not None and api_key.allowed_projects.exists():
            return Response(
                {"error_code": "PERMISSION_DENIED", "message": "API key with restricted project scope cannot create new experiments."},
                status=status.HTTP_403_FORBIDDEN,
            )

        exp_name = request.data.get("name", "").strip() or "default-experiment"
        target_project = project or ModelProject.objects.filter(owner__tenant_id=tenant_id, name=exp_name, deletion_state="active").first()
        if not target_project:
            target_project = ModelProject.objects.filter(owner__tenant_id=tenant_id, deletion_state="active").first()

        if target_project:
            return Response({"experiment_id": str(target_project.public_id)})

        # Create a new project for this experiment if none exists
        new_project = ModelProject.objects.create(
            owner=user,
            name=exp_name,
            description=f"Auto-created experiment for tenant {tenant_id}",
        )
        return Response({"experiment_id": str(new_project.public_id)})


class MLflowExperimentsGetView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        job, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        exp_id = request.query_params.get("experiment_id") or ""
        target_project = None
        try:
            proj_uuid = uuid.UUID(str(exp_id))
            target_project = ModelProject.objects.filter(public_id=proj_uuid, owner__tenant_id=tenant_id).first()
        except (ValueError, TypeError):
            pass

        if not target_project:
            if not exp_id and job:
                target_project = job.project
            elif not exp_id:
                target_project = project or _scoped_projects_queryset(tenant_id, api_key).first()

        if not target_project:
            return Response(
                {"error_code": "RESOURCE_DOES_NOT_EXIST", "message": f"Experiment '{exp_id}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if job is not None and job.project_id != target_project.id:
            return Response(
                {"error_code": "PERMISSION_DENIED", "message": "Capability token is only authorized for its assigned experiment."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if api_key is not None and not _is_project_allowed_for_api_key(api_key, target_project):
            return Response(
                {"error_code": "PERMISSION_DENIED", "message": "API key is not authorized for this experiment."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {
                "experiment": {
                    "experiment_id": str(target_project.public_id),
                    "name": target_project.name,
                    "artifact_location": _project_mlflow_artifact_uri(target_project),
                    "lifecycle_stage": "active",
                }
            }
        )

