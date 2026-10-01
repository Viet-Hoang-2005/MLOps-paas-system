"""Bounded resource-scoped log pages; clients never supply LogQL."""

import json
from collections import Counter
from datetime import timedelta
from uuid import UUID

import requests
from django.conf import settings
from django.core import signing
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from common.logging import runtime_line

PAGE_SIZE = 500
CURSOR_SALT = "runtime-logs-v1"
NAMESPACES = {
    "build": "mlops-execution|mlops-control-plane",
    "deployment": "mlops-execution|mlops-model-runtimes|mlops-control-plane",
    "drift": "mlops-execution|mlops-control-plane",
    "training": "mlops-execution|user-jobs|mlops-control-plane",
}


def _cursor(value, resource, kind):
    task_id = str(UUID(str(resource.public_id)))
    initial_ns = int(resource.created_at.timestamp() * 1_000_000_000)
    initial = {"task": task_id, "kind": kind, "ns": initial_ns, "skip": 0}
    if not value:
        return initial
    try:
        decoded = signing.loads(value, salt=CURSOR_SALT, max_age=7 * 86400)
        if (
            not isinstance(decoded, dict)
            or decoded.get("task") != task_id
            or decoded.get("kind") != kind
            or type(decoded.get("ns")) is not int
            or type(decoded.get("skip")) is not int
            or not 0 <= decoded["skip"] <= 1000
            or not initial_ns <= decoded["ns"] <= int(timezone.now().timestamp() * 1_000_000_000)
        ):
            raise ValueError
        return decoded
    except (signing.BadSignature, ValueError, TypeError) as exc:
        raise ValidationError({"cursor": "Invalid or expired log cursor."}) from exc


def runtime_log_page(request, resource, kind, fallback):
    """Call only after resolving resource ownership with a tenant-scoped selector."""
    try:
        offset = int(request.query_params.get("offset", "0"))
        if offset < 0:
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise ValidationError({"offset": "Must be a non-negative integer."}) from exc
    backend = resource.monitor.backend if kind == "drift" else getattr(resource, "backend", "")
    if not settings.LOKI_URL or backend != "argo":
        lines, next_offset = fallback(resource, offset)
        return {"logs": lines, "next_offset": next_offset}

    state = _cursor(request.query_params.get("cursor"), resource, kind)
    result = {
        "logs": [],
        "next_offset": offset,
        "next_cursor": request.query_params.get("cursor") or signing.dumps(state, salt=CURSOR_SALT, compress=True),
        "source": "loki",
        "has_more": False,
    }
    earliest = int((timezone.now() - timedelta(days=7)).timestamp() * 1_000_000_000)
    start = max(state["ns"], earliest)
    # Leave time for the collector's last push, including exit-handler output.
    end = int((timezone.now() - timedelta(seconds=2)).timestamp() * 1_000_000_000)
    if end < start:
        return result
    query = (
        f'{{namespace=~{json.dumps(NAMESPACES[kind])},task_kind={json.dumps(kind)}}}'
        f' | task_id={json.dumps(state["task"])}'
    )
    try:
        response = requests.get(
            f"{settings.LOKI_URL.rstrip('/')}/loki/api/v1/query_range",
            params={
                "query": query,
                "start": str(start),
                "end": str(end),
                "direction": "forward",
                "limit": PAGE_SIZE + state["skip"],
            },
            timeout=(2, 5),
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success" or payload["data"]["resultType"] != "streams":
            raise ValueError("Invalid log response")
        entries = []
        for stream in payload["data"]["result"]:
            stream_key = json.dumps(stream.get("stream") or {}, sort_keys=True)
            for value in stream.get("values") or []:
                entries.append((int(value[0]), stream_key, str(value[1])))
        entries.sort()
    except (requests.RequestException, ValueError, KeyError, TypeError):
        # Preserve the cursor during outages. Task status remains available.
        return {**result, "log_error": "unavailable"}
    skipped = 0
    page = []
    for entry in entries:
        if entry[0] == state["ns"] and skipped < state["skip"]:
            skipped += 1
            continue
        page.append(entry)
    page = page[:PAGE_SIZE]
    if page:
        last_ns = page[-1][0]
        count = Counter(entry[0] for entry in page)[last_ns]
        if last_ns == state["ns"]:
            count += state["skip"]
        state = {**state, "ns": last_ns, "skip": count}
        result["next_cursor"] = signing.dumps(state, salt=CURSOR_SALT, compress=True)
        result["next_offset"] = offset + len(page)
        result["logs"] = [runtime_line(entry[2]) for entry in page]
        result["has_more"] = len(page) == PAGE_SIZE
    return result
