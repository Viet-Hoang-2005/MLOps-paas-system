import uuid
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.training.selectors import job_for_user, jobs_for_user


class TrainingJobMetricsHistoryEndpoint(APIView):
    def get(self, request, job_id):
        job = job_for_user(request.user, job_id)
        metrics = job.step_metrics.order_by("name", "step").values("name", "value", "step", "timestamp")

        grouped = {}
        for m in metrics:
            name = m["name"]
            if name not in grouped:
                grouped[name] = []
            grouped[name].append(
                {
                    "step": m["step"],
                    "value": m["value"],
                    "timestamp": m["timestamp"].isoformat() if m["timestamp"] else None,
                }
            )

        params = {p.name: p.value for p in job.hyperparameters.all()}
        if not params and isinstance(job.tracking, dict) and "params" in job.tracking:
            params = job.tracking["params"]

        metrics_summary = dict(job.tracking.get("metrics", {})) if isinstance(job.tracking, dict) else {}

        return Response(
            {
                "job_id": str(job.public_id),
                "name": job.name,
                "status": job.status,
                "model_flavor": job.model_flavor,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "runtime_seconds": job.runtime_seconds,
                "params": params,
                "metrics_summary": metrics_summary,
                "series": [{"name": k, "points": v} for k, v in grouped.items()],
            }
        )


class TrainingJobsCompareEndpoint(APIView):
    def get(self, request):
        raw_ids = request.query_params.get("job_ids", "")
        if not raw_ids:
            return Response({"runs": []})

        id_strings = [item.strip() for item in raw_ids.split(",") if item.strip()][:10]
        parsed_uuids = []
        for s in id_strings:
            try:
                parsed_uuids.append(uuid.UUID(s))
            except (ValueError, TypeError):
                continue

        if not parsed_uuids:
            return Response({"runs": []})

        user_jobs = jobs_for_user(request.user).filter(public_id__in=parsed_uuids).prefetch_related("step_metrics", "hyperparameters")

        runs = []
        all_metric_names = set()
        all_param_names = set()

        for job in user_jobs:
            params = {p.name: p.value for p in job.hyperparameters.all()}
            if not params and isinstance(job.tracking, dict) and "params" in job.tracking:
                params = job.tracking["params"]

            all_param_names.update(params.keys())

            grouped = {}
            for m in job.step_metrics.order_by("step"):
                name = m.name
                all_metric_names.add(name)
                if name not in grouped:
                    grouped[name] = []
                grouped[name].append(
                    {
                        "step": m.step,
                        "value": m.value,
                    }
                )

            metrics_summary = dict(job.tracking.get("metrics", {})) if isinstance(job.tracking, dict) else {}
            all_metric_names.update(metrics_summary.keys())

            runs.append(
                {
                    "job_id": str(job.public_id),
                    "name": job.name,
                    "status": job.status,
                    "model_flavor": job.model_flavor,
                    "runtime_seconds": job.runtime_seconds,
                    "created_at": job.created_at.isoformat(),
                    "params": params,
                    "metrics_summary": metrics_summary,
                    "series": [{"name": k, "points": v} for k, v in grouped.items()],
                }
            )

        return Response(
            {
                "runs": runs,
                "metric_names": sorted(all_metric_names),
                "param_names": sorted(all_param_names),
            }
        )

