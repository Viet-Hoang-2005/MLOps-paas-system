from rest_framework import serializers

from apps.training.jobs.models import TrainingJob


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
