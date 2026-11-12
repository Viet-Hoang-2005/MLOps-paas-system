"""Tests use synthetic features, local files and mocked tracking/device probes."""

import importlib.util
import json
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import ModuleType, SimpleNamespace

import joblib
import numpy as np
import pandas as pd
import pytest

FOLDER = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("nids_trainer", FOLDER / "train.py")
trainer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trainer)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "input"
    (root / "data").mkdir(parents=True)
    for name in ("config.json", "feature_schema.json"):
        shutil.copyfile(FOLDER / name, root / name)
    config = json.loads((root / "config.json").read_text())
    config.update(n_estimators=35, early_stopping_rounds=4, device="cpu", max_threads=1)
    (root / "config.json").write_text(json.dumps(config))
    names = json.loads((root / "feature_schema.json").read_text())
    random = np.random.default_rng(42)
    frame = pd.DataFrame(random.normal(size=(200, 52)), columns=names)
    frame["Label"] = np.where(frame[names[0]] > 0, "DDoS", "BENIGN")
    frame.to_csv(root / "data/train.csv", index=False)
    monkeypatch.setenv("SM_CHANNEL_TRAIN", str(root))
    for key, name in (
        ("SM_MODEL_DIR", "model"),
        ("SM_OUTPUT_DIR", "output"),
        ("MLOPS_WORK_DIR", "work"),
    ):
        monkeypatch.setenv(key, str(tmp_path / name))
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.chdir(tmp_path)  # restore cwd after main's chdir
    return root, config, names, frame


def test_schema_matches_existing_dataset():
    # Test fixture schema is authoritative and ordered; do not need real CSV data.
    names = json.loads((FOLDER / "feature_schema.json").read_text())
    assert len(names) == len(set(names)) == 52
    assert names[0] == "Destination Port" and names[-1] == "Idle Min"


@pytest.mark.parametrize(
    "option,value",
    [
        ("device", "gpu"),
        ("classification_mode", "other"),
        ("n_estimators", 0),
        ("seed", True),
        ("test_fraction", 0),
        ("validation_fraction", 1),
        ("subsample", 1.1),
        ("max_threads", -1),
        ("learning_rate", float("nan")),
        ("unknown", 1),
    ],
)
def test_config_rejects_invalid_options(workspace, option, value):
    root, config, _, _ = workspace
    config[option] = value
    (root / "config.json").write_text(json.dumps(config))
    with pytest.raises(ValueError):
        trainer.load_config(root, "config.json")


def test_paths_cannot_escape_input(workspace):
    root, _, _, _ = workspace
    (root.parent / "outside.csv").write_text("data")
    for path in ("../outside.csv", "missing.csv", str(root.parent / "outside.csv")):
        with pytest.raises(ValueError):
            trainer.input_file(root, path)


@pytest.mark.parametrize("change", ["missing", "duplicate", "whitespace", "wrong_type"])
def test_invalid_feature_schema(workspace, change):
    root, _, names, _ = workspace
    if change == "missing":
        names.pop()
    elif change == "duplicate":
        names[1] = names[0]
    elif change == "whitespace":
        names[0] = " " + names[0]
    else:
        names = {"features": names}
    (root / "feature_schema.json").write_text(json.dumps(names))
    with pytest.raises(ValueError, match="52 distinct"):
        trainer.load_schema(root, "feature_schema.json")


def test_data_cleaning_mapping_and_split(workspace):
    root, config, names, frame = workspace
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    frame.loc[len(frame)] = frame.iloc[1]
    frame.loc[len(frame) - 1, names[1]] = float("inf")
    frame.loc[len(frame)] = frame.iloc[2]
    frame.loc[len(frame) - 1, "Label"] = " "
    frame.to_csv(root / "data/train.csv", index=False)
    x, y, classes, stats = trainer.load_data(root / "data/train.csv", names, config)
    assert classes == ["BENIGN", "ATTACK"]
    assert stats["invalid_rows_removed"] == 2
    assert stats["duplicate_rows_removed"] == 1
    assert len(x) == 200 and list(x.columns) == names
    parts = trainer.split_data(x, y, config)
    assert [len(parts[key][1]) for key in ("train", "validation", "test")] == [
        140,
        30,
        30,
    ]
    sets = [set(values[0].index) for values in parts.values()]
    assert not sets[0] & sets[1] and not sets[0] & sets[2] and not sets[1] & sets[2]
    assert all(set(values[1]) == {0, 1} for values in parts.values())


@pytest.mark.parametrize(
    "change", ["missing", "extra", "duplicate", "conflict", "single", "invalid_numeric"]
)
def test_bad_csv_is_rejected(workspace, change):
    root, config, names, frame = workspace
    path = root / "data/train.csv"
    if change == "missing":
        frame = frame.drop(columns=names[0])
    elif change == "extra":
        frame["Source IP"] = "127.0.0.1"
    elif change == "duplicate":
        frame.columns = [" Label " if col == names[0] else col for col in frame.columns]
    elif change == "conflict":
        row = frame.iloc[[0]].copy()
        row["Label"] = "BENIGN" if row.Label.iloc[0] != "BENIGN" else "ATTACK"
        frame = pd.concat([frame, row])
    elif change == "single":
        frame["Label"] = "BENIGN"
    else:
        frame[names[0]] = "broken"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError):
        trainer.load_data(path, names, config)


def test_tiny_classes_never_disable_stratification(workspace):
    _, config, names, _ = workspace
    with pytest.raises(ValueError, match="samples|class"):
        trainer.split_data(
            pd.DataFrame(np.ones((6, 52)), columns=names),
            np.array([0, 0, 0, 0, 0, 1]),
            config,
        )


def test_multiclass_mapping_deterministic(workspace):
    root, config, names, frame = workspace
    config["classification_mode"] = "multiclass"
    frame["Label"] = [" PortScan ", "BENIGN", "DDoS", "WebAttack"] * 50
    frame.to_csv(root / "data/train.csv", index=False)
    _, y, classes, _ = trainer.load_data(root / "data/train.csv", names, config)
    assert classes == ["BENIGN", "DDoS", "PortScan", "WebAttack"]
    assert list(y[:4]) == [2, 0, 1, 3]


def test_cgroup_v1_v2_and_fractional_cpu(tmp_path, monkeypatch):
    monkeypatch.setattr(trainer.os, "cpu_count", lambda: 16)
    monkeypatch.setattr(
        trainer.os, "sched_getaffinity", lambda _: set(range(8)), raising=False
    )
    (tmp_path / "cpu.max").write_text("350000 100000")
    assert trainer.cpu_threads(cgroup_root=tmp_path) == 3
    assert trainer.cpu_threads(2, tmp_path) == 2
    (tmp_path / "cpu.max").write_text("50000 100000")
    assert trainer.cpu_threads(cgroup_root=tmp_path) == 1
    (tmp_path / "cpu.max").write_text("max 100000")
    (tmp_path / "cpu").mkdir()
    (tmp_path / "cpu/cpu.cfs_quota_us").write_text("200000")
    (tmp_path / "cpu/cpu.cfs_period_us").write_text("100000")
    assert trainer.cpu_threads(cgroup_root=tmp_path) == 2


def test_gpu_selection(monkeypatch):
    monkeypatch.setattr(trainer.shutil, "which", lambda _: None)
    assert trainer.select_device("auto") == "cpu"
    with pytest.raises(RuntimeError):
        trainer.select_device("cuda")
    monkeypatch.setattr(trainer.shutil, "which", lambda _: "nvidia-smi")
    monkeypatch.setattr(
        trainer.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="GPU-test", stderr=""),
    )
    assert trainer.select_device("auto") == trainer.select_device("cuda") == "cuda"
    assert trainer.select_device("cpu") == "cpu"
    monkeypatch.setattr(
        trainer.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=1, stdout="", stderr="driver failed"
        ),
    )
    with pytest.raises(RuntimeError):
        trainer.select_device("auto")


def test_gpu_probe_timeout_and_multiple_devices(monkeypatch):
    monkeypatch.setattr(trainer.shutil, "which", lambda _: "nvidia-smi")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("nvidia-smi", 10)

    monkeypatch.setattr(trainer.subprocess, "run", timeout)
    with pytest.raises(RuntimeError):
        trainer.select_device("auto")
    monkeypatch.setattr(
        trainer.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="GPU-a\nGPU-b", stderr=""),
    )
    with pytest.raises(RuntimeError, match="one GPU"):
        trainer.select_device("auto")


def test_progress_detects_silent_xgboost_cpu_fallback():
    callback = trainer.Progress(SimpleNamespace(send=lambda **k: None), "cuda")
    fake = SimpleNamespace(
        save_config=lambda: json.dumps(
            {"learner": {"generic_param": {"device": "cpu"}}}
        )
    )
    with pytest.raises(RuntimeError, match="fell back"):
        callback.after_iteration(fake, 0, {"train": {"logloss": [0.5]}})


def test_tracking_is_job_scoped_and_stops_after_first_error(monkeypatch, capsys):
    calls = []

    class Client:
        def __init__(self, tracking_uri):
            calls.append(("uri", tracking_uri))

        def create_run(self, experiment_id, tags):
            calls.append(("create", experiment_id))
            return SimpleNamespace(
                info=SimpleNamespace(run_id="authenticated-job-uuid")
            )

        def log_batch(self, run_id, **kwargs):
            calls.append((run_id, kwargs))
            if kwargs.get("params"):
                raise RuntimeError("secret-should-not-appear")

    tracking_module = ModuleType("mlflow.tracking")
    tracking_module.MlflowClient = Client
    entities_module = ModuleType("mlflow.entities")
    entities_module.Metric = lambda *args: args
    entities_module.Param = lambda *args: args
    monkeypatch.setitem(sys.modules, "mlflow.tracking", tracking_module)
    monkeypatch.setitem(sys.modules, "mlflow.entities", entities_module)
    monkeypatch.setenv(
        "MLFLOW_TRACKING_URI", "http://control-plane:8000/api/2.0/mlflow/"
    )
    tracking = trainer.Tracking()
    callback = trainer.Progress(tracking, "cpu")
    callback.after_iteration(None, 3, {"validation": {"logloss": [0.8, 0.5]}})
    assert calls[0] == ("uri", "http://control-plane:8000")
    assert calls[1] == ("create", "0")
    assert calls[2][0] == "authenticated-job-uuid"
    assert calls[2][1]["metrics"][0][0:2] == ("validation_logloss", 0.5)
    assert calls[2][1]["metrics"][0][3] == 3
    tracking.send(params={"device": "cpu"})
    size = len(calls)
    tracking.send(metrics={"accuracy": 1})
    assert len(calls) == size and tracking.warning
    assert "secret-should-not-appear" not in capsys.readouterr().out


def test_undefined_precision_is_not_fabricated(workspace):
    _, _, names, _ = workspace
    fake = SimpleNamespace(
        predict=lambda x: np.zeros(4),
        predict_proba=lambda x: np.array([[0.9, 0.1]] * 4),
    )
    metrics, report = trainer.evaluate(
        fake,
        pd.DataFrame(np.zeros((4, 52)), columns=names),
        np.array([0, 0, 1, 1]),
        ["BENIGN", "ATTACK"],
    )
    assert report["per_class"]["ATTACK"]["precision"] is None
    assert report["undefined_metrics"] and metrics["attack_recall"] == 0
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("multiclass", [False, True])
def test_cpu_training_export_and_outputs(workspace, monkeypatch, capsys, multiclass):
    root, config, names, frame = workspace
    if multiclass:
        config["classification_mode"] = "multiclass"
        frame["Label"] = np.where(
            frame[names[0]] > 0.4,
            "DDoS",
            np.where(frame[names[0]] < -0.4, "BENIGN", "PortScan"),
        )
        frame.to_csv(root / "data/train.csv", index=False)
    (root / "config.json").write_text(json.dumps(config))
    before = {
        p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    trainer.main([])
    assert {
        p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()
    } == before
    model_dir = root.parent / "model"
    model = joblib.load(model_dir / "model.joblib")
    assert trainer.booster_device(model.get_booster()) == "cpu"
    assert model.get_booster().num_boosted_rounds() == model.best_iteration + 1
    assert model.callbacks is None
    assert set(model.predict(frame[names])) <= set(range(3 if multiclass else 2))
    assert len(list(model_dir.glob("*.joblib"))) == 1
    schema = json.loads((root.parent / "output/input_schema.json").read_text())
    assert schema["required"] == schema["x-feature-order"] == names
    assert (
        set(schema["properties"]) == set(names)
        and schema["additionalProperties"] is False
    )
    metrics = json.loads((root.parent / "output/metrics.json").read_text())
    assert metrics["accuracy"] > 0.7
    insights = json.loads((root.parent / "output/training_report.json").read_text())
    assert (
        len(
            insights["learning_curves"][
                "validation_logloss" if not multiclass else "validation_mlogloss"
            ]
        )
        >= model.best_iteration + 1
    )
    assert "METRIC_JSON" not in capsys.readouterr().out


def test_rejects_output_inside_input(workspace, monkeypatch):
    root, _, _, _ = workspace
    monkeypatch.setenv("SM_MODEL_DIR", str(root / "model"))
    with pytest.raises(ValueError, match="read-only"):
        trainer.main([])


def test_export_keeps_best_predictions_after_real_early_stop(workspace, monkeypatch):
    root, config, names, frame = workspace
    config.update(n_estimators=100, early_stopping_rounds=2)
    frame["Label"] = np.random.default_rng(19).choice(["BENIGN", "DDoS"], len(frame))
    frame.to_csv(root / "data/train.csv", index=False)
    (root / "config.json").write_text(json.dumps(config))
    original_fit = trainer.xgb.XGBClassifier.fit
    observed = {}

    def fit(model, *args, **kwargs):
        np.testing.assert_array_equal(
            kwargs["sample_weight"],
            trainer.compute_sample_weight("balanced", args[1]),
        )
        result = original_fit(model, *args, **kwargs)
        observed["probabilities"] = model.predict_proba(frame[names])
        observed["fitted_rounds"] = model.get_booster().num_boosted_rounds()
        return result

    monkeypatch.setattr(trainer.xgb.XGBClassifier, "fit", fit)
    trainer.main([])
    model = joblib.load(root.parent / "model/model.joblib")
    assert model.get_booster().num_boosted_rounds() < observed["fitted_rounds"] < 100
    np.testing.assert_allclose(
        model.predict_proba(frame[names]), observed["probabilities"], rtol=1e-7
    )


def test_tracking_failure_still_writes_outputs(workspace, monkeypatch):
    root, _, _, _ = workspace

    class FailedTracking:
        warning = "tracking unavailable"

        def send(self, **kwargs):
            pass

    monkeypatch.setattr(trainer, "Tracking", FailedTracking)
    trainer.main([])
    assert (root.parent / "model/model.joblib").is_file()
    report = json.loads((root.parent / "output/training_report.json").read_text())
    assert report["tracking_warning"] == "tracking unavailable"
    assert (
        json.loads((root.parent / "output/metrics.json").read_text())["accuracy"] > 0.7
    )


def test_real_mlflow_sdk_uses_supported_rest_routes(monkeypatch):
    # Exercise SDK serialization/routing, not just a fake MlflowClient method.
    pytest.importorskip("mlflow")
    recorded = []
    job_id = "c75ca0c04eaa4001a0fca69a76332dd9"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            recorded.append((self.path, payload, self.headers.get("Authorization")))
            if self.path == "/api/2.0/mlflow/runs/create":
                response = {
                    "run": {
                        "info": {
                            "run_id": job_id,
                            "run_uuid": job_id,
                            "experiment_id": "0",
                            "status": "RUNNING",
                            "start_time": 0,
                            "artifact_uri": "mlflow-artifacts:/test",
                            "lifecycle_stage": "active",
                        },
                        "data": {"metrics": [], "params": [], "tags": []},
                    }
                }
            elif self.path == "/api/2.0/mlflow/runs/log-batch":
                response = {}
            else:
                self.send_error(404)
                return
            raw = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        monkeypatch.setenv(
            "MLFLOW_TRACKING_URI",
            f"http://127.0.0.1:{server.server_port}/api/2.0/mlflow",
        )
        monkeypatch.setenv("MLFLOW_TRACKING_TOKEN", "synthetic-test-token")
        tracking = trainer.Tracking()
        tracking.send(params={"device": "cpu"}, metrics={"train_logloss": 0.4}, step=7)
        assert tracking.warning is None
        assert [entry[0] for entry in recorded] == [
            "/api/2.0/mlflow/runs/create",
            "/api/2.0/mlflow/runs/log-batch",
        ]
        assert recorded[1][1]["run_id"] == job_id
        assert recorded[1][1]["metrics"][0]["step"] == 7
        assert all(entry[2] == "Bearer synthetic-test-token" for entry in recorded)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
