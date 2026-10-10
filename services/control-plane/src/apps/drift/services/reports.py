from django.conf import settings

from infrastructure.storage.paths import drift_run_prefix

REPORT_ARTIFACT_FIELDS = {
    "report_html_uri": ("html_s3_uri", "report.html"),
    "report_json_uri": ("report_json_s3_uri", "report.json"),
    "summary_uri": ("summary_json_s3_uri", "summary.json"),
}


def report_artifact_uris(run, summary):
    artifacts = summary.get("report_artifacts") if isinstance(summary, dict) else None
    if not isinstance(artifacts, dict):
        return {}

    project = run.monitor.version.project
    prefix = drift_run_prefix(
        project.owner.tenant_id,
        project.public_id,
        run.monitor.public_id,
        run.public_id,
    )
    bucket = settings.AWS_STORAGE_BUCKET_NAME
    expected_uris = {
        field: f"s3://{bucket}/{prefix}{filename}"
        for field, (_artifact_key, filename) in REPORT_ARTIFACT_FIELDS.items()
    }

    return {
        field: artifacts[artifact_key]
        for field, (artifact_key, _filename) in REPORT_ARTIFACT_FIELDS.items()
        if isinstance(artifacts.get(artifact_key), str) and artifacts[artifact_key] == expected_uris[field]
    }


def report_uri_for_run(run, field):
    stored_uri = getattr(run, field)
    if stored_uri:
        return stored_uri

    fallback_uris = getattr(run, "_resolved_report_uris", None)
    if fallback_uris is None:
        fallback_uris = report_artifact_uris(run, run.summary)
        run._resolved_report_uris = fallback_uris
    return fallback_uris.get(field, "")


def get_drift_report_data(run):
    import json
    import logging
    from infrastructure.storage import S3Storage

    logger = logging.getLogger(__name__)
    storage = S3Storage()
    html_uri = report_uri_for_run(run, "report_html_uri")
    json_uri = report_uri_for_run(run, "report_json_uri")

    html_url = storage.presigned_get(html_uri, 900) if html_uri else None
    json_url = storage.presigned_get(json_uri, 900) if json_uri else None

    summary = run.summary if isinstance(run.summary, dict) else {}

    parsed_report = None
    if json_uri:
        try:
            raw_bytes = storage.read(json_uri)
            parsed_report = json.loads(raw_bytes.decode("utf-8"))
        except Exception:
            logger.warning(
                "Failed to load report.json for run %s from %s",
                run.public_id,
                json_uri,
                exc_info=True,
            )

    metrics_list = (
        parsed_report.get("metrics", [])
        if isinstance(parsed_report, dict)
        else []
    )

    dataset_drift_metric = {}
    data_drift_table_metric = {}

    for metric_item in metrics_list:
        metric_name = metric_item.get("metric")
        if metric_name == "DatasetDriftMetric":
            dataset_drift_metric = metric_item.get("result", {})
        elif metric_name == "DataDriftTable":
            data_drift_table_metric = metric_item.get("result", {})

    dataset_drift = (
        dataset_drift_metric.get("dataset_drift")
        if "dataset_drift" in dataset_drift_metric
        else summary.get("dataset_drift", summary.get("has_drift", False))
    )
    drift_share = dataset_drift_metric.get(
        "drift_share", summary.get("drift_threshold", 0.6)
    )
    drift_score = (
        dataset_drift_metric.get("share_of_drifted_columns")
        if "share_of_drifted_columns" in dataset_drift_metric
        else summary.get(
            "drift_score", summary.get("share_drifted_features", 0.0)
        )
    )
    number_of_columns = (
        dataset_drift_metric.get("number_of_columns")
        if "number_of_columns" in dataset_drift_metric
        else summary.get("number_of_features", 0)
    )
    number_of_drifted_columns = (
        dataset_drift_metric.get("number_of_drifted_columns")
        if "number_of_drifted_columns" in dataset_drift_metric
        else summary.get("number_of_drifted_features", 0)
    )

    drift_by_columns = data_drift_table_metric.get("drift_by_columns", {})
    columns = []

    if drift_by_columns:
        for col_name, col_data in drift_by_columns.items():
            if not isinstance(col_data, dict):
                continue
            columns.append(
                {
                    "column_name": col_data.get("column_name", col_name),
                    "column_type": col_data.get("column_type", "num"),
                    "stattest_name": col_data.get(
                        "stattest_name", "Statistical test"
                    ),
                    "stattest_threshold": col_data.get(
                        "stattest_threshold", 0.0
                    ),
                    "drift_score": col_data.get("drift_score", 0.0),
                    "drift_detected": bool(
                        col_data.get("drift_detected", False)
                    ),
                    "current": col_data.get("current", {}),
                    "reference": col_data.get("reference", {}),
                }
            )
    else:
        drifted_names = set(summary.get("drifted_feature_names", []))
        for col_name in drifted_names:
            columns.append(
                {
                    "column_name": col_name,
                    "column_type": "num",
                    "stattest_name": "Evidently Drift",
                    "stattest_threshold": drift_share,
                    "drift_score": 1.0,
                    "drift_detected": True,
                    "current": {},
                    "reference": {},
                }
            )

    columns.sort(
        key=lambda c: (not c["drift_detected"], c["column_name"].lower())
    )

    version_str = ""
    try:
        version_obj = run.monitor.version
        version_str = str(getattr(version_obj, "version", ""))
    except Exception:
        pass

    project_id = ""
    project_name = ""
    try:
        proj = run.monitor.version.project
        project_id = str(proj.public_id)
        project_name = proj.name
    except Exception:
        pass

    return {
        "run_id": str(run.public_id),
        "monitor_id": str(run.monitor.public_id),
        "project_id": project_id,
        "project_name": project_name,
        "version": version_str,
        "status": run.status,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "dataset_drift": bool(dataset_drift),
        "drift_share": float(drift_share) if drift_share is not None else 0.6,
        "drift_score": float(drift_score) if drift_score is not None else 0.0,
        "number_of_columns": (
            int(number_of_columns)
            if number_of_columns is not None
            else len(columns)
        ),
        "number_of_drifted_columns": (
            int(number_of_drifted_columns)
            if number_of_drifted_columns is not None
            else 0
        ),
        "production_records": summary.get(
            "production_records", summary.get("samples", 0)
        ),
        "data_quality": summary.get("data_quality", {}),
        "columns": columns,
        "artifacts": {
            "html_url": html_url,
            "json_url": json_url,
        },
    }

