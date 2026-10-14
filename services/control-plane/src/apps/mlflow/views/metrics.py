import json
import logging
from datetime import datetime, timezone as dt_timezone

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.training.models import (
    TrainingJobMetric,
    TrainingJobParam,
    TrainingJobTag,
)
from common.redis_client import redis_client
from ..auth import (
    _require_auth,
    _resolve_target_job,
)

logger = logging.getLogger(__name__)


class MLflowRunsLogBatchView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        job_from_auth, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        run_id = request.data.get("run_id")
        job, err_job = _resolve_target_job(job_from_auth, run_id, tenant_id, api_key=api_key, for_mutation=True)
        if err_job:
            return err_job

        metrics = request.data.get("metrics") or []
        params = request.data.get("params") or []
        tags = request.data.get("tags") or []

        # 1. Bulk insert metrics
        metric_objects = []
        tracking_metrics_update = {}
        for m in metrics:
            k = str(m.get("key", "")).strip()[:160]
            try:
                val = float(m.get("value"))
            except (TypeError, ValueError):
                continue
            step = int(m.get("step") or 0)
            raw_ts = m.get("timestamp")
            ts = datetime.fromtimestamp(raw_ts / 1000.0, tz=dt_timezone.utc) if raw_ts else timezone.now()
            metric_objects.append(
                TrainingJobMetric(job=job, name=k, value=val, step=step, timestamp=ts)
            )
            tracking_metrics_update[k] = val

        if metric_objects:
            TrainingJobMetric.objects.bulk_create(metric_objects)

        # 2. Upsert params
        tracking_params_update = {}
        for p in params:
            k = str(p.get("key", "")).strip()[:160]
            v = str(p.get("value", ""))[:500]
            if k:
                TrainingJobParam.objects.update_or_create(job=job, name=k, defaults={"value": v})
                tracking_params_update[k] = v

        # 3. Upsert tags
        for t in tags:
            k = str(t.get("key", "")).strip()[:160]
            v = str(t.get("value", ""))[:500]
            if k:
                TrainingJobTag.objects.update_or_create(job=job, name=k, defaults={"value": v})

        # 4. Update job tracking summary
        if tracking_metrics_update or tracking_params_update:
            current_tracking = dict(job.tracking or {})
            if "metrics" not in current_tracking:
                current_tracking["metrics"] = {}
            if "params" not in current_tracking:
                current_tracking["params"] = {}
            current_tracking["metrics"].update(tracking_metrics_update)
            current_tracking["params"].update(tracking_params_update)
            job.tracking = current_tracking
            job.save(update_fields=["tracking", "updated_at"])

        # 5. Realtime emission to Redis
        try:
            r = redis_client(1)
            event_payload = json.dumps(
                {
                    "job_id": str(job.public_id),
                    "metrics": [{"key": m.name, "value": m.value, "step": m.step} for m in metric_objects[:50]],
                    "params": tracking_params_update,
                }
            )
            r.publish(f"training_metrics:{job.public_id}", event_payload)
            r.rpush(f"training_metric_events:{job.public_id}", event_payload)
            r.expire(f"training_metric_events:{job.public_id}", 86400 * 7)
        except Exception as exc:
            logger.warning("Failed to emit realtime metric event to Redis: %s", exc)

        return Response({})


class MLflowRunsLogMetricView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        job_from_auth, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        run_id = request.data.get("run_id")
        job, err_job = _resolve_target_job(job_from_auth, run_id, tenant_id, api_key=api_key, for_mutation=True)
        if err_job:
            return err_job

        key = str(request.data.get("key", "")).strip()[:160]
        try:
            val = float(request.data.get("value"))
        except (TypeError, ValueError):
            return Response({"error_code": "INVALID_PARAMETER_VALUE", "message": "Metric value must be float"}, status=status.HTTP_400_BAD_REQUEST)

        step = int(request.data.get("step") or 0)
        raw_ts = request.data.get("timestamp")
        ts = datetime.fromtimestamp(raw_ts / 1000.0, tz=dt_timezone.utc) if raw_ts else timezone.now()

        TrainingJobMetric.objects.create(job=job, name=key, value=val, step=step, timestamp=ts)

        current_tracking = dict(job.tracking or {})
        if "metrics" not in current_tracking:
            current_tracking["metrics"] = {}
        current_tracking["metrics"][key] = val
        job.tracking = current_tracking
        job.save(update_fields=["tracking", "updated_at"])

        return Response({})


class MLflowRunsLogParameterView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        job_from_auth, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        run_id = request.data.get("run_id")
        job, err_job = _resolve_target_job(job_from_auth, run_id, tenant_id, api_key=api_key, for_mutation=True)
        if err_job:
            return err_job

        key = str(request.data.get("key", "")).strip()[:160]
        value = str(request.data.get("value", ""))[:500]

        TrainingJobParam.objects.update_or_create(job=job, name=key, defaults={"value": value})

        current_tracking = dict(job.tracking or {})
        if "params" not in current_tracking:
            current_tracking["params"] = {}
        current_tracking["params"][key] = value
        job.tracking = current_tracking
        job.save(update_fields=["tracking", "updated_at"])

        return Response({})


class MLflowRunsSetTagView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        job_from_auth, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        run_id = request.data.get("run_id")
        job, err_job = _resolve_target_job(job_from_auth, run_id, tenant_id, api_key=api_key, for_mutation=True)
        if err_job:
            return err_job

        key = str(request.data.get("key", "")).strip()[:160]
        value = str(request.data.get("value", ""))[:500]

        TrainingJobTag.objects.update_or_create(job=job, name=key, defaults={"value": value})
        return Response({})


class MLflowMetricsGetHistoryView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        job_from_auth, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        run_id = request.query_params.get("run_id")
        metric_key = request.query_params.get("metric_key") or ""
        job, err_job = _resolve_target_job(job_from_auth, run_id, tenant_id, api_key=api_key)
        if err_job:
            return err_job

        points = job.step_metrics.filter(name=metric_key).order_by("step")
        return Response(
            {
                "metrics": [
                    {
                        "key": p.name,
                        "value": p.value,
                        "step": p.step,
                        "timestamp": int(p.timestamp.timestamp() * 1000) if p.timestamp else 0,
                    }
                    for p in points
                ]
            }
        )

