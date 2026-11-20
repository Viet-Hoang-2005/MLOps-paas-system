"""Read bounded Docker runtime logs for an owned deployment."""

from collections import Counter
from datetime import datetime

import docker.errors
import requests
from django.core import signing

from common.logging import runtime_line
from infrastructure.docker import DockerClient
from infrastructure.execution.local_containers import ContainerOwnershipError, owned_container
from infrastructure.runtime_logs import CURSOR_SALT, PAGE_SIZE, _cursor


def docker_runtime_page(request, deployment):
    state = _cursor(request.query_params.get("cursor"), deployment, "deployment_runtime")
    result = {"logs": [], "next_offset": 0, "source": "docker", "has_more": False,
              "next_cursor": signing.dumps(state, salt=CURSOR_SALT, compress=True)}
    if not deployment.external_deployment_id:
        return {**result, "log_error": "unavailable"}
    stream = None
    try:
        container = owned_container(DockerClient(timeout=5).client, deployment, "deploy")
        stream = container.logs(stdout=True, stderr=True, timestamps=True, stream=True, follow=False,
                                since=max(0, state["ns"] // 1_000_000_000 - 1))
        entries = []
        skipped = 0
        for chunk in stream:
            for line in chunk.decode("utf-8", errors="replace").splitlines():
                stamp, separator, message = line.partition(" ")
                if not separator:
                    continue
                date, _, fraction = stamp.rstrip("Z").partition(".")
                ns = int(datetime.fromisoformat(date + "+00:00").timestamp()) * 1_000_000_000
                ns += int((fraction + "000000000")[:9])
                if ns < state["ns"]:
                    continue
                if ns == state["ns"] and skipped < state["skip"]:
                    skipped += 1
                    continue
                entries.append((ns, message))
                if len(entries) > PAGE_SIZE:
                    break
            if len(entries) > PAGE_SIZE:
                break
        page = entries[:PAGE_SIZE]
        if page:
            last_ns = page[-1][0]
            count = Counter(ns for ns, _ in page)[last_ns]
            if last_ns == state["ns"]:
                count += state["skip"]
            state.update(ns=last_ns, skip=count)
            result.update(logs=[runtime_line(line) for _, line in page], has_more=len(entries) > PAGE_SIZE,
                          next_cursor=signing.dumps(state, salt=CURSOR_SALT, compress=True))
        return result
    except (docker.errors.DockerException, requests.RequestException, ContainerOwnershipError, ValueError, OSError):
        return {**result, "log_error": "unavailable"}
    finally:
        if stream is not None and hasattr(stream, "close"):
            stream.close()
