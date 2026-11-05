import pytest


@pytest.fixture(autouse=True)
def legacy_docker_capacity(request, monkeypatch, settings):
    """Existing API/GPU tests use a deterministic Docker capacity, not a real daemon."""
    if request.node.path.name not in {"test_jobs.py", "test_local_gpu.py", "test_gpu_models.py", "test_quota.py"}:
        return
    from apps.training.services import local_resources
    snapshot = {"status": "available", "reason": "", "daemon_id": "test-docker", "total_vcpu": 8,
                "total_memory_mb": 12288, "cpu_profiles": [
                    {"id": "small", "vcpu": 1, "memory_mb": 2048},
                    {"id": "medium", "vcpu": 2, "memory_mb": 4096},
                    {"id": "large", "vcpu": 4, "memory_mb": 8192}]}
    monkeypatch.setattr(local_resources, "capacity", lambda **kwargs: snapshot)
    monkeypatch.setattr(local_resources, "_check_unmanaged", lambda daemon_id: None)
    if request.node.path.name in {"test_jobs.py", "test_local_gpu.py"}:
        settings.TRAINING_EXECUTION_WATCH_ENABLED = True
