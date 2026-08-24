from common.api.permissions import HasInternalWebhookSecret
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.drift.models import DriftRun
from apps.drift.services.automatic import request_automatic_drift_runs


class AutomaticDriftSignalSerializer(serializers.Serializer):
    model_version_id = serializers.UUIDField()


class DriftRunWebhookEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (HasInternalWebhookSecret,)

    def post(self, request, run_id):
        with transaction.atomic():
            run = DriftRun.objects.select_for_update().get(public_id=run_id)
            if run.status in {"completed", "failed", "cancelled"}:
                return Response({"status": run.status, "duplicate": True})
            summary = request.data.get("drift_summary") or request.data.get("summary") or {}
            run.summary = summary
            run.drift_score = summary.get("drift_score", summary.get("share_of_drifted_columns"))
            run.has_drift = summary.get("has_drift", summary.get("dataset_drift"))
            run.status = "completed"
            run.completed_at = timezone.now()
            run.save(update_fields=["summary", "drift_score", "has_drift", "status", "completed_at"])
        return Response({"status": run.status})


class AutomaticDriftWebhookEndpoint(APIView):
    """Accept durable Consumer signals; only the Control Plane creates runs."""

    authentication_classes = ()
    permission_classes = (HasInternalWebhookSecret,)

    def post(self, request):
        serializer = AutomaticDriftSignalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        triggered = request_automatic_drift_runs(str(serializer.validated_data["model_version_id"]))
        return Response({"status": "accepted", "triggered_runs": triggered}, status=202)
