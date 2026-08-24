import json

from django.db import connections

from .models import EventOutbox

PRODUCTION_DATA_COLUMNS = (
    "id",
    "project_id",
    "model_version_id",
    "timestamp",
    "features",
    "prediction",
)


def pending_outbox_events(limit=100):
    return EventOutbox.objects.filter(published_at__isnull=True).order_by("created_at")[:limit]


def latest_production_data(project, limit=None, *, db_connection=None):
    connection = db_connection or connections["default"]
    if "paas_production_logs" not in connection.introspection.table_names():
        return []

    table = '"public"."paas_production_logs"' if connection.vendor == "postgresql" else '"paas_production_logs"'
    limit_clause = " LIMIT %s" if limit is not None else ""
    params = [str(project.owner.tenant_id), str(project.public_id)]
    if limit is not None:
        params.append(limit)

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, project_id, model_version_id, timestamp, features, prediction
            FROM {table}
            WHERE tenant_id = %s AND project_id = %s
            ORDER BY timestamp DESC NULLS LAST, id DESC
            {limit_clause}
            """,
            params,
        )
        rows = cursor.fetchall()

    results = []
    for row in rows:
        record = dict(zip(PRODUCTION_DATA_COLUMNS, row, strict=True))
        if isinstance(record["features"], str):
            try:
                record["features"] = json.loads(record["features"])
            except (TypeError, ValueError):
                record["features"] = {}
        results.append(record)
    return results
