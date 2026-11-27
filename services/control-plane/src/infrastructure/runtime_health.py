"""Bounded readiness probe; no Docker/Kubernetes API or caller-supplied URL."""

import json
import time

import requests


DEEP_LEARNING_FLAVORS = frozenset({"pytorch", "tensorflow", "keras"})


def is_dl_flavor(flavor) -> bool:
    """Return whether a model flavor is served by the BentoML deep-learning runtime."""
    return str(flavor or "").strip().lower() in DEEP_LEARNING_FLAVORS


def healthy_payload(payload, *, project_id, version_id):
    return (
        isinstance(payload, dict)
        and payload.get("status") == "healthy"
        and payload.get("model_loaded") is True
        and payload.get("project_id") == str(project_id)
        and payload.get("model_version_id") == str(version_id)
    )


class RuntimeHealthProbe:
    MAX_BYTES = 64 * 1024

    def check(self, *, url, flavor, project_id, version_id):
        if not url:
            return "unknown"
        method = "POST" if is_dl_flavor(flavor) else "GET"
        try:
            with requests.Session() as session:
                session.trust_env = False
                with session.request(
                    method,
                    f"{url.rstrip('/')}/health",
                    **({"json": {}} if method == "POST" else {}),
                    timeout=(1, 2),
                    allow_redirects=False,
                    stream=True,
                ) as response:
                    if response.status_code != 200:
                        return "unhealthy"
                    deadline = time.monotonic() + 5
                    body = bytearray()
                    for chunk in response.iter_content(chunk_size=4096):
                        body.extend(chunk)
                        if len(body) > self.MAX_BYTES or time.monotonic() > deadline:
                            return "unhealthy"
                    payload = json.loads(body)
            if not isinstance(payload, dict):
                return "unhealthy"
            healthy = healthy_payload(payload, project_id=project_id, version_id=version_id)
            return "healthy" if healthy else "unhealthy"
        except (requests.RequestException, ValueError, UnicodeError):
            return "unhealthy"
