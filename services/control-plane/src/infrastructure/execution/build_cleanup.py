"""Quiesce one build before deleting its build-scoped output."""

from infrastructure.execution.local_containers import remove_container


def stop_build_for_deletion(build):
    if build.backend == "argo":
        # The Events-only client cannot confirm Workflow termination. Never remove
        # outputs while a dispatched Workflow may still publish a new image.
        if build.started_at and not build.execution_completed_at:
            raise RuntimeError("Waiting for the dispatched Argo build to finish before deleting its output.")
        return
    remove_container(build, "build")
