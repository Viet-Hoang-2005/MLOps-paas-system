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
