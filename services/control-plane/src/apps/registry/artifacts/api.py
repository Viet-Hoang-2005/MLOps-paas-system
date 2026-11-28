from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.registry.artifacts.supplemental import add_supplemental_artifacts, get_version_reference_preview
from apps.registry.versions.selectors import version_for_user
from apps.registry.versions.serializers import ModelVersionSerializer
from common.api.downloads import scoped_download_response
from common.api.exceptions import Conflict
from infrastructure.storage.paths import version_prefix


class ModelVersionSupplementalArtifactsEndpoint(APIView):
    def post(self, request, version_id):
        version = version_for_user(request.user, version_id)
        updated = add_supplemental_artifacts(
            version=version,
            actor=request.user,
            source_code_file=request.FILES.get("source_code_file"),
            reference_data_file=request.FILES.get("reference_data_file"),
            csv_upload_token=request.data.get("csv_upload_token"),
            label_mapping_file=request.FILES.get("label_mapping_file"),
            input_schema_file=request.FILES.get("input_schema_file"),
            metrics_file=request.FILES.get("metrics_file"),
            params_file=request.FILES.get("params_file"),
            model_insights_file=request.FILES.get("model_insights_file"),
            feature_importance_file=request.FILES.get("feature_importance_file"),
        )
        return Response(ModelVersionSerializer(updated).data)


class ModelVersionReferencePreviewEndpoint(APIView):
    def get(self, request, version_id):
        version = version_for_user(request.user, version_id)
        return Response(get_version_reference_preview(version))


class ModelVersionReferenceDownloadEndpoint(APIView):
    def get(self, request, version_id):
        version = version_for_user(request.user, version_id)
        project = version.project
        if version.deletion_requested or project.deletion_state != "active" or not project.is_active:
            raise Conflict("This model version is unavailable.")
        asset = version.artifacts.filter(kind="reference_data").first()
        if asset is None:
            raise NotFound("Reference dataset is unavailable.")
        return scoped_download_response(
            asset.uri,
            prefix=version_prefix(project.owner.tenant_id, project.public_id, version.public_id) + "/",
            filename=asset.name,
        )
