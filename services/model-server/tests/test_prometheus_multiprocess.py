import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from src.uvicorn_entrypoint import main, metrics_directory


def run_python(script, directory):
    env = {**os.environ, "PROMETHEUS_MULTIPROC_DIR": directory}
    return subprocess.check_output([sys.executable, "-c", script], env=env, text=True, timeout=15)


def test_two_workers_and_restart_aggregate_without_double_counting():
    worker = """
from prometheus_client import Counter, Histogram
c = Counter('test_predictions_total', 'Predictions', ['tenant_id'])
h = Histogram('test_latency_seconds', 'Latency')
c.labels('tenant-1').inc(3)
h.observe(0.5)
"""
    scrape = """
from src.prometheus_metrics import metrics_response
print(metrics_response().body.decode())
"""
    with metrics_directory() as directory:
        run_python(worker, directory)
        run_python(worker, directory)
        for _ in range(2):
            output = run_python(scrape, directory)
            assert 'test_predictions_total{tenant_id="tenant-1"} 6.0' in output
            assert output.count('test_predictions_total{tenant_id="tenant-1"}') == 1
            assert 'test_latency_seconds_count 2.0' in output
            assert 'test_latency_seconds_sum 1.0' in output
    assert not Path(directory).exists()
    with metrics_directory() as restarted:
        assert restarted != directory
        assert 'test_predictions_total' not in run_python(scrape, restarted)
        run_python(worker, restarted)
        assert 'test_predictions_total{tenant_id="tenant-1"} 3.0' in run_python(scrape, restarted)


def test_parent_only_uses_fresh_child_and_preserves_root(tmp_path, monkeypatch):
    unrelated = tmp_path / "keep.txt"
    unrelated.write_text("not a metric")
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    with metrics_directory() as directory:
        assert Path(directory).parent == tmp_path
        assert os.environ["PROMETHEUS_MULTIPROC_DIR"] == directory
    assert unrelated.read_text() == "not a metric"
    assert os.environ["PROMETHEUS_MULTIPROC_DIR"] == str(tmp_path)


def test_entrypoint_sets_directory_before_starting_workers(monkeypatch):
    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)
    monkeypatch.setattr(sys, "argv", ["server", "src.main:app", "--service", "model-server", "--port", "5000"])
    seen = []

    def start(app, **kwargs):
        directory = os.environ["PROMETHEUS_MULTIPROC_DIR"]
        assert Path(directory).is_dir()
        assert kwargs["workers"] == 2
        assert app == "src.main:app"
        seen.append(directory)

    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=start))
    main()
    assert len(seen) == 1
    assert not Path(seen[0]).exists()
    assert "PROMETHEUS_MULTIPROC_DIR" not in os.environ
