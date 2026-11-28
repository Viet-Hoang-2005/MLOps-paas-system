"""Lightweight build callback entrypoint, without model framework imports."""

import json
import logging
import os
import sys
import time
from pathlib import Path

import requests

from src import io
from src.logging_utils import RuntimeLog, bind_context, configure, get_logger, reset_context


def main():
    started = time.monotonic()
    configure("model-packager")
    log = RuntimeLog(get_logger("model-packager"))
    build_id = os.environ.get("BUILD_ID", "")
    tokens = bind_context(build_id=build_id, operation="NOTIFY_BUILD")
    try:
        if not build_id:
            raise ValueError("Missing BUILD_ID")
        log.event(logging.INFO, "build_execution_started", "Starting NOTIFY_BUILD process", duration_ms=0)
        workspace = Path(os.environ.get("BUILD_WORKSPACE_DIR", "/workspace"))
        payload = io.finite_json(json.loads((workspace / "webhook_payload.json").read_text(encoding="utf-8")))
        image_uri = os.environ.get("IMAGE_URI", "").strip()
        if image_uri:
            payload["image_uri"] = image_uri
        digest = workspace / "image-digest"
        if digest.exists():
            payload["image_digest"] = digest.read_text(encoding="utf-8").strip()
        secret = os.environ.get("CONTROL_PLANE_WEBHOOK_SECRET", "").strip()
        headers = {"X-Control-Plane-Secret": secret} if secret else {}
        log.detail(f"Sending post-build notification for build {build_id}...")
        io.post_webhook(os.environ.get("CONTROL_PLANE_WEBHOOK_URL", ""), payload, requests, headers)
        log.protocol("NOTIFY_EOF_SUCCESS")
        log.event(logging.INFO, "build_execution_completed", "Build notification completed", duration_ms=round((time.monotonic() - started) * 1000, 3))
    except Exception as exc:
        log.event(logging.ERROR, "build_execution_failed", "Build notification failed", error_type=type(exc).__name__)
        sys.exit(1)
    finally:
        reset_context(tokens)


if __name__ == "__main__":
    main()
