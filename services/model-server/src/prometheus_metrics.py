"""One scrape aggregates every Uvicorn worker in this pod, not every pod."""

import os

from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, CollectorRegistry, generate_latest, multiprocess


def metrics_response():
    registry = REGISTRY
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    return Response(generate_latest(registry), headers={"Content-Type": CONTENT_TYPE_LATEST})
