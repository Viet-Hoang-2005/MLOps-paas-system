"""Quiesce one build before deleting its build-scoped output."""

from infrastructure.execution.local_containers import remove_container


def stop_build_for_deletion(build):
    if build.backend == "argo":
        from infrastructure.execution import build_backend

        return build_backend("argo").cancel(build)["confirmed"]
    remove_container(build, "build")
