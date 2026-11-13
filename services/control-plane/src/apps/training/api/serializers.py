from rest_framework import serializers

from apps.catalog.models import ModelProject
from apps.observability.models import LifecycleEvent
from apps.training.models import TrainingJob, TrainingOutput


class TrainingDraftSettingsSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1, required=False)
    entry_point = serializers.CharField(max_length=512, allow_blank=True, required=False)
    environment = serializers.DictField(
        child=serializers.CharField(allow_blank=True, trim_whitespace=False), required=False
    )
    model_flavor = serializers.ChoiceField(choices=TrainingJob.MODEL_FLAVORS, required=False)
    vcpu = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    memory_mb = serializers.IntegerField(min_value=512, allow_null=True, required=False)
    max_runtime_seconds = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    accelerator_type = serializers.ChoiceField(choices=TrainingJob.ACCELERATORS, required=False)
    accelerator_count = serializers.IntegerField(min_value=0, max_value=1, required=False)
    accelerator_model = serializers.ChoiceField(choices=["", "t4", "a10g"], required=False)
    local_gpu_id = serializers.CharField(max_length=80, allow_blank=True, required=False)

    def validate(self, attrs):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({field: "Unsupported draft setting." for field in unknown})
        return attrs


class TrainingSubmissionSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1)
    run_key = serializers.UUIDField()


class TrainingOutputSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = TrainingOutput
        fields = (
            "id",
            "kind",
            "relative_path",
            "s3_uri",
            "checksum",
            "size_bytes",
            "content_type",
            "metadata",
            "created_at",
        )


class TrainingJobEventSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = LifecycleEvent
        fields = ("id", "event_type", "message", "metadata", "created_at")


class TrainingJobBuildRequestSerializer(serializers.Serializer):
    output_revision = serializers.IntegerField(min_value=1)


class NewTrainingProjectSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField(max_length=160, trim_whitespace=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    access_mode = serializers.ChoiceField(choices=ModelProject.ACCESS_MODES, default="private")


class TrainingJobProjectRequestSerializer(serializers.Serializer):
    model_id = serializers.UUIDField()
    artifacts = serializers.JSONField(required=False, default=dict)
    project_id = serializers.UUIDField(required=False)
    new_project = NewTrainingProjectSerializer(required=False)
    output_revision = serializers.IntegerField(min_value=1)

    def validate(self, attrs):
        if ("project_id" in attrs) == ("new_project" in attrs):
            raise serializers.ValidationError("Choose an existing project or provide a new project.")
        return attrs


class TrainingJobSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    project_id = serializers.UUIDField(source="project.public_id", read_only=True, allow_null=True)
    entries = serializers.SerializerMethodField()
    secrets = serializers.SerializerMethodField()
    secrets_available = serializers.SerializerMethodField()
    workspace_id = serializers.UUIDField(source="workspace.public_id", read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True, allow_null=True)
    environment = serializers.JSONField(source="environment_snapshot", read_only=True)
    outputs = serializers.SerializerMethodField()

    def get_outputs(self, instance):
        from apps.training.services.output_index import public_outputs

        return TrainingOutputSerializer(public_outputs(instance), many=True).data

    output_available = serializers.SerializerMethodField()
    registration_build = serializers.SerializerMethodField()
    model_status = serializers.SerializerMethodField()
    deletion_pending = serializers.SerializerMethodField()

    class Meta:
        model = TrainingJob
        fields = (
            "id",
            "project_id",
            "input_contract",
            "input_revision",
            "run_key",
            "environment",
            "entries",
            "secrets",
            "secrets_available",
            "workspace_id",
            "project_name",
            "submitted_at",
            "model_flavor",
            "entry_point",
            "requirements_text",
            "code_snapshot_uri",
            "data_snapshot_uri",
            "output_revision",
            "mlflow_artifact_uri",
            "mlflow_run_id",
            "backend",
            "external_job_id",
            "celery_task_id",
            "status",
            "observation_status",
            "observation_error",
            "execution_deadline_at",
            "runtime_started_at",
            "vcpu",
            "memory_mb",
            "max_runtime_seconds",
            "accelerator_type",
            "accelerator_count",
            "accelerator_model",
            "local_gpu_id",
            "tracking",
            "error_message",
            "started_at",
            "completed_at",
            "runtime_seconds",
            "outputs_purged_at",
            "output_available",
            "registration_build",
            "model_status",
            "deletion_requested_at",
            "deletion_error",
            "deletion_pending",
            "outputs",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "input_contract",
            "input_revision",
            "run_key",
            "observation_status",
            "observation_error",
            "execution_deadline_at",
            "runtime_started_at",
            "backend",
            "code_snapshot_uri",
            "data_snapshot_uri",
            "output_revision",
            "mlflow_artifact_uri",
            "external_job_id",
            "celery_task_id",
            "status",
            "tracking",
            "error_message",
            "started_at",
            "completed_at",
            "runtime_seconds",
            "outputs_purged_at",
            "deletion_requested_at",
            "deletion_error",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {"requirements_text": {"required": False, "allow_blank": True}}

    def get_entries(self, instance):
        return []

    @staticmethod
    def get_secrets(instance):
        return [{"name": name} for name in instance.secret_snapshot]

    @staticmethod
    def get_secrets_available(instance):
        from apps.training.services.workspaces import ServiceUnavailable, cipher

        try:
            cipher()
            return True
        except ServiceUnavailable:
            return False

    @staticmethod
    def get_output_available(instance):
        from apps.training.services.output_index import public_outputs

        return (
            instance.status == "completed"
            and instance.outputs_purged_at is None
            and instance.tracking.get("output_contract") == 2
            and public_outputs(instance).filter(kind="model").exists()
        )

    @staticmethod
    def get_registration_build(instance):
        builds = list(instance.builds.all())
        build = max(builds, key=lambda item: item.created_at, default=None)
        if not build:
            return None
        return TrainingBuildSerializer(build).data

    @staticmethod
    def get_model_status(instance):
        """Return the lifecycle state of the model produced by this training job."""
        if instance.status != "completed":
            return "none"

        ready_builds = [
            build for build in instance.builds.all() if build.status == "ready" and build.version_id is not None
        ]
        if not ready_builds:
            return "trained"

        active_id = instance.project.active_deployment_id if instance.project_id else None
        for build in ready_builds:
            if any(deployment.pk == active_id for deployment in build.version.deployments.all()):
                return "deployed"
        return "built"

    @staticmethod
    def get_deletion_pending(instance):
        return instance.deletion_requested_at is not None


class TrainingBuildSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    project_id = serializers.UUIDField(source="project.public_id", read_only=True)
    source_job_id = serializers.SerializerMethodField()
    version_id = serializers.UUIDField(source="version.public_id", allow_null=True, read_only=True)
    version_number = serializers.CharField(source="version.version", allow_null=True, read_only=True)
    flavor = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    image_uri = serializers.CharField(read_only=True)
    image_digest = serializers.CharField(read_only=True)
    error_message = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    @staticmethod
    def get_source_job_id(instance):
        return instance.source_job_reference or (instance.source_job.public_id if instance.source_job_id else None)
