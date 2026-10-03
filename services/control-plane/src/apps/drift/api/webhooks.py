from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.drift.models import DriftRun
from apps.catalog.models import ModelProject
from apps.drift.services.automatic import request_automatic_drift_runs
from apps.drift.services.reports import report_artifact_uris
from common.api.permissions import HasInternalWebhookSecret
from common.logging import record_transition


class AutomaticDriftSignalSerializer(serializers.Serializer):
    model_version_id = serializers.UUIDField()


class DriftRunWebhookEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (HasInternalWebhookSecret,)

    def post(self, request, run_id):
        with transaction.atomic():
            project_id = (
                DriftRun.objects.filter(public_id=run_id).values_list("monitor__version__project_id", flat=True).first()
            )
            project = ModelProject.objects.select_for_update().filter(pk=project_id).first()
            if not project:
                return Response({"status": "deleted", "ignored": True})
            run = DriftRun.objects.select_for_update().filter(public_id=run_id).first()
            if not run:
                return Response({"status": "deleted", "ignored": True})
            if project.deletion_state != "active" or run.status in {"cancelled", "failed"}:
                return Response({"status": run.status, "duplicate": True})
            summary = request.data.get("drift_summary") or request.data.get("summary") or {}
            drift_score = summary.get("drift_score", summary.get("share_of_drifted_columns"))
            has_drift = summary.get("has_drift", summary.get("dataset_drift"))
            report_uris = report_artifact_uris(run, summary)

            if run.status == "completed" and run.summary and run.drift_score is not None:
                report_fields = []
                for field, uri in report_uris.items():
                    if uri and not getattr(run, field):
                        setattr(run, field, uri)
                        report_fields.append(field)
                if report_fields:
                    run.save(update_fields=report_fields)
                return Response({"status": run.status, "duplicate": True})

            already_completed = run.status == "completed"
            run.summary = summary
            run.drift_score = drift_score
            run.has_drift = has_drift
            run.status = "completed"
            run.completed_at = run.completed_at or timezone.now()
            run.error_message = ""
            update_fields = ["summary", "drift_score", "has_drift", "status", "completed_at", "error_message"]
            for field, uri in report_uris.items():
                if uri and not getattr(run, field):
                    setattr(run, field, uri)
                    update_fields.append(field)
            run.save(update_fields=update_fields)
            record_transition(
                run,
                "completed",
                phase="summary_updated" if already_completed else None,
                source="webhook",
            )
            if run.has_drift:
                from apps.drift.tasks import handle_drift_detected

                transaction.on_commit(lambda: handle_drift_detected.delay(str(run.public_id)))
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
