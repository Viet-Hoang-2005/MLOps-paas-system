from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ModelProject
from apps.drift.models import DriftRun
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
        summary = request.data.get("drift_summary") or request.data.get("summary") or {}
        is_skipped = (
            summary.get("status") == "skipped"
            or request.data.get("status") == "skipped"
            or "insufficient" in str(summary.get("reason", "")).lower()
        )
        verified_summary = None
        if settings.EXECUTION_WATCH_ENABLED and not is_skipped:
            from apps.observability.services.executions import _completion_data, resource_for
            candidate = resource_for("drift", run_id)
            if candidate and candidate.status not in {"completed", "failed", "cancelled", "skipped"} and not candidate.execution_stop_requested and candidate.monitor.version.project.deletion_state == "active":
                try:
                    verified_summary = _completion_data(candidate, "drift")
                except Exception:
                    return Response({"detail": "Drift output verification is unavailable."}, status=503)
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
            if project.deletion_state != "active" or run.status in {"cancelled", "failed", "skipped"} or run.execution_stop_requested:
                return Response({"status": run.status, "duplicate": True})

            if is_skipped:
                run.summary = summary
                run.drift_score = None
                run.has_drift = False
                run.status = "skipped"
                run.completed_at = run.completed_at or timezone.now()
                run.error_message = summary.get("reason", "Insufficient production samples.")
                run.observation_status = "cleanup_pending"
                run.execution_stop_requested = True
                run.next_execution_check_at = timezone.now()
                run.save(update_fields=[
                    "summary", "drift_score", "has_drift", "status",
                    "completed_at", "error_message", "observation_status",
                    "execution_stop_requested", "next_execution_check_at"
                ])
                record_transition(run, "skipped")
                return Response({"status": "skipped"})

            summary = verified_summary if verified_summary is not None else summary
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
            run.observation_status = "cleanup_pending"
            run.execution_stop_requested = True
            run.next_execution_check_at = timezone.now()
            update_fields = ["summary", "drift_score", "has_drift", "status", "completed_at", "error_message", "observation_status", "execution_stop_requested", "next_execution_check_at"]
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
