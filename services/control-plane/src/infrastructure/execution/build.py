from django.conf import settings
from django.db import transaction

from infrastructure.execution.argo_backend import _ArgoBackend
from infrastructure.execution.build_inputs import label_mapping_input
from infrastructure.execution.docker_client import DockerClient
from infrastructure.execution.docker_environment import _logging_environment
from infrastructure.execution.local_containers import remove_container, start_container
from infrastructure.images.references import build_image_tag, image_repository
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import build_prefix, build_result_key


class ArgoBuildBackend(_ArgoBackend):
    setting_name = "ARGO_BUILD_WEBHOOK_URL"

    def run(self, build):
        project = build.project
        source = build.input_assets.filter(kind__in=("source_artifact", "training_output")).first()
        if source is None and build.version_id:
            source = build.version.artifacts.filter(kind__in=("source", "training_output")).first()
        if not source:
            raise RuntimeError("The build has no source artifact.")
        source_uri = getattr(source, "s3_uri", "") or source.uri
        label_mapping_url, label_mapping_filename = label_mapping_input(build, self.storage)
        package_uri = (
            f"s3://{self.storage.bucket}/"
            f"{build_prefix(project.owner.tenant_id, project.public_id, build.public_id)}"
            "/artifacts/model-package.zip"
        )
        build.package_uri = package_uri
        build.save(update_fields=["package_uri", "updated_at"])
        payload = {
            "build_id": str(build.public_id),
            "project_id": str(project.public_id),
            "tenant_id": project.owner.tenant_id,
            "image_repository": image_repository(
                project.public_id,
                registry=settings.HARBOR_REGISTRY_URL,
                registry_project=settings.HARBOR_USER_PROJECT,
            ),
            "image_tag": build_image_tag(build.public_id),
            "flavor": build.flavor,
            "task_type": "TEST_ZIP" if build.artifact_format == "mlflow_zip" else "BUILD",
            "requirements_text": build.requirements_snapshot,
            "source_artifact_name": source.name,
            "source_type": "training_job" if build.source_job_id else "manual_upload",
            "source_download_url": self.storage.presigned_get(source_uri, 14400),
            "label_mapping_download_url": label_mapping_url,
            "label_mapping_filename": label_mapping_filename,
            "input_schema_download_url": self.storage.presigned_get(
                build.input_assets.get(kind="input_schema").s3_uri, 14400
            )
            if build.input_assets.filter(kind="input_schema").exists()
            else "",
            "output_upload_url": self.storage.presigned_put(package_uri, 14400),
            "result_upload_url": self.storage.presigned_put(
                f"s3://{self.storage.bucket}/{build_result_key(project.owner.tenant_id, project.public_id, build.public_id)}",
                14400,
                "application/json",
            ),
            "control_plane_webhook_url": (
                f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/webhooks/builds/{build.public_id}/"
            ),
        }
        from common.api.exceptions import Conflict

        with transaction.atomic():
            locked_project = type(project).objects.select_for_update().get(pk=project.pk)
            current = type(build).objects.select_for_update().get(pk=build.pk)
            if locked_project.deletion_state != "active" or current.deletion_state != "active":
                raise Conflict("The build or project is being deleted.")
            if current.status in {"cancelled", "failed"}:
                return {"dispatched": False, "cancelled": True}
        return self.trigger(payload)

    def cancel(self, build):
        if not (build.started_at or build.execution_deadline_at or build.execution_completed_at or build.status == "building"):
            return {"confirmed": True}
        return self.request_runtime_stop(build, "build")
class DockerBuildBackend:
    def __init__(self, docker_client=None, storage=None):
        self.docker = docker_client or DockerClient()
        self.storage = storage or S3Storage()

    def run(self, build):
        project = build.project
        source = build.input_assets.filter(kind__in=("source_artifact", "training_output")).first()
        if source is None and build.version_id:
            source = (
                build.version.artifacts.filter(kind__in=("source", "training_output")).order_by("-created_at").first()
            )
        if not source:
            raise RuntimeError("The build has no source artifact.")
        source_uri = getattr(source, "s3_uri", "") or source.uri
        label_mapping_url, label_mapping_filename = label_mapping_input(build, self.storage)
        package_root = build_prefix(project.owner.tenant_id, project.public_id, build.public_id)
        package_uri = f"s3://{self.storage.bucket}/{package_root}/artifacts/model-package.zip"
        build.package_uri = package_uri
        build.save(update_fields=["package_uri", "updated_at"])
        webhook = f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/webhooks/builds/{build.public_id}/"
        task_type = "TEST_ZIP" if build.artifact_format == "mlflow_zip" else "BUILD"
        environment = {
            **_logging_environment(),
            "TASK_TYPE": task_type,
            "BUILD_ID": str(build.public_id),
            "PROJECT_ID": str(project.public_id),
            "TENANT_ID": project.owner.tenant_id,
            "IMAGE_REPOSITORY": image_repository(project.public_id),
            "IMAGE_TAG": build_image_tag(build.public_id),
            "FLAVOR": build.flavor,
            "REQUIREMENTS_TEXT": build.requirements_snapshot,
            "SOURCE_ARTIFACT_NAME": source.name,
            "SOURCE_TYPE": "training_job" if build.source_job_id else "manual_upload",
            "SOURCE_DOWNLOAD_URL": self.storage.presigned_get(source_uri, 14400),
            "LABEL_MAPPING_DOWNLOAD_URL": label_mapping_url,
            "LABEL_MAPPING_FILENAME": label_mapping_filename,
            "INPUT_SCHEMA_DOWNLOAD_URL": self.storage.presigned_get(
                build.input_assets.get(kind="input_schema").s3_uri, 14400
            )
            if build.input_assets.filter(kind="input_schema").exists()
            else "",
            "OUTPUT_UPLOAD_URL": self.storage.presigned_put(package_uri, 14400),
            "CONTROL_PLANE_WEBHOOK_URL": webhook,
            "CONTROL_PLANE_WEBHOOK_SECRET": settings.CONTROL_PLANE_WEBHOOK_SECRET,
            "HARBOR_REGISTRY_URL": settings.HARBOR_REGISTRY_URL,
            "HARBOR_USER_PROJECT": settings.HARBOR_USER_PROJECT,
            "HARBOR_USERNAME": settings.HARBOR_USERNAME,
            "HARBOR_PASSWORD": settings.HARBOR_PASSWORD,
            "REDIS_URL": settings.REDIS_URL,
        }
        container = start_container(
            self.docker,
            build,
            "build",
            image="mlops-paas-model-packager",
            name=f"build-{build.public_id}",
            environment=environment,
            network=settings.DOCKER_NETWORK_NAME,
            volumes={"/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"}},
        )
        return {"dispatched": True, "container_id": container.id}

    def cancel(self, build):
        remove_container(build, "build", self.docker.client)
