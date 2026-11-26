"""Tests for Diabetes-Logreg MLOps-PaaS training workspace script."""

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import joblib
import numpy as np
import pandas as pd
import pytest

FOLDER = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("diabetes_paas_trainer", FOLDER / "train.py")
trainer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trainer)


def _synthetic_frame(rows: int = 120, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    data = {
        "time_in_hospital": rng.integers(1, 14, size=rows),
        "num_lab_procedures": rng.integers(1, 90, size=rows),
        "num_procedures": rng.integers(0, 6, size=rows),
        "num_medications": rng.integers(1, 40, size=rows),
        "number_diagnoses": rng.integers(1, 10, size=rows),
        "gender": rng.choice(["Female", "Male"], size=rows),
        "age": rng.choice(
            ["30 years or younger", "30-60 years", "Over 60 years"], size=rows
        ),
        "admission_source_id": rng.choice(["Emergency", "Referral", "Other"], size=rows),
        "medical_specialty": rng.choice(
            ["Missing", "InternalMedicine", "Surgery", "Other"], size=rows
        ),
        "primary_diagnosis": rng.choice(
            ["Diabetes", "Respiratory Issues", "Other"], size=rows
        ),
        "max_glu_serum": rng.choice(["Missing", "Norm", ">200", ">300"], size=rows),
        "A1Cresult": rng.choice(["Missing", "Norm", ">7", ">8"], size=rows),
        "insulin": rng.choice(["No", "Steady", "Up", "Down"], size=rows),
        "change": rng.choice(["No", "Ch"], size=rows),
        "diabetesMed": rng.choice(["Yes", "No"], size=rows),
        "medicare": rng.integers(0, 2, size=rows),
        "medicaid": rng.integers(0, 2, size=rows),
        "had_emergency": rng.integers(0, 2, size=rows),
        "had_inpatient_days": rng.integers(0, 2, size=rows),
        "had_outpatient_days": rng.integers(0, 2, size=rows),
        "Label": rng.choice(
            ["No Readmission within 30 Days", "Readmission within 30 Days"],
            size=rows,
            p=[0.7, 0.3],
        ),
    }
    return pd.DataFrame(data)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "input"
    (root / "data").mkdir(parents=True)
    for name in ("config.json", "feature_schema.json"):
        shutil.copyfile(FOLDER / name, root / name)
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
    frame = _synthetic_frame()
    frame.to_csv(root / "data" / "training_data.csv", index=False)

    monkeypatch.setenv("SM_CHANNEL_TRAIN", str(root))
    for key, name in (
        ("SM_MODEL_DIR", "model"),
        ("SM_OUTPUT_DIR", "output"),
        ("MLOPS_WORK_DIR", "work"),
    ):
        monkeypatch.setenv(key, str(tmp_path / name))
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.chdir(tmp_path)
    return root, config, frame


def test_schema_has_20_distinct_features():
    num, cat, all_features = trainer.load_schema(FOLDER, "feature_schema.json")
    assert len(num) == 10
    assert len(cat) == 10
    assert len(all_features) == len(set(all_features)) == 20


@pytest.mark.parametrize(
    "option,value",
    [
        ("seed", True),
        ("max_iter", 0),
        ("validation_fraction", 0),
        ("validation_fraction", 1),
        ("threshold", 1.2),
        ("C", -0.5),
        ("solver", "invalid"),
        ("class_weight", "auto"),
        ("unknown", 1),
    ],
)
def test_config_rejects_invalid_options(workspace, option, value):
    root, config, _ = workspace
    config[option] = value
    (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError):
        trainer.load_config(root, "config.json")


@pytest.mark.parametrize("change", ["missing", "extra", "single_class", "bad_numeric"])
def test_bad_csv_is_rejected(workspace, change):
    root, config, frame = workspace
    num, cat, all_features = trainer.load_schema(root, "feature_schema.json")
    path = root / "data" / "training_data.csv"
    if change == "missing":
        frame = frame.drop(columns=[all_features[0]])
    elif change == "extra":
        frame["patient_nbr"] = 123
    elif change == "single_class":
        frame["Label"] = "No Readmission within 30 Days"
    else:
        frame[num[0]] = "invalid"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError):
        trainer.load_data(path, num, cat, all_features, config)


def test_end_to_end_training_outputs_and_parity(workspace, capsys):
    root, _, frame = workspace
    before = {
        p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    trainer.main([])
    assert {
        p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()
    } == before

    model_dir = root.parent / "model"
    output_dir = root.parent / "output"
    model = joblib.load(model_dir / "model.joblib")
    assert len(list(model_dir.glob("*.joblib"))) == 1

    feature_cols = [c for c in frame.columns if c != "Label"]
    preds = model.predict(frame[feature_cols])
    assert set(preds) <= {0, 1}

    label_mapping = json.loads((output_dir / "label_mapping.json").read_text())
    assert label_mapping == {
        "0": "No Readmission within 30 Days",
        "1": "Readmission within 30 Days",
    }

    input_schema = json.loads((output_dir / "input_schema.json").read_text())
    assert input_schema["type"] == "object"
    assert input_schema["required"] == input_schema["x-feature-order"] == feature_cols
    assert input_schema["additionalProperties"] is False

    metrics = json.loads((output_dir / "metrics.json").read_text())
    assert all(isinstance(v, (int, float)) for v in metrics.values())
    assert "roc_auc" in metrics and "pr_auc" in metrics

    feat_imp = json.loads((output_dir / "feature_importance.json").read_text())
    assert isinstance(feat_imp["feature_importance"], dict)
    assert len(feat_imp["feature_importance"]) > 0

    insights = json.loads((output_dir / "model_insights.json").read_text())
    assert insights["kind"] == "feature_importance"
    assert "top_positive_risk_factors" in insights
    assert "METRIC_JSON" not in capsys.readouterr().out


def test_tracking_error_does_not_abort_training(workspace, monkeypatch):
    root, _, _ = workspace
    calls = []

    class BrokenClient:
        def __init__(self, tracking_uri):
            calls.append(tracking_uri)

        def create_run(self, experiment_id, tags):
            return SimpleNamespace(info=SimpleNamespace(run_id="job-123"))

        def log_batch(self, run_id, **kwargs):
            raise RuntimeError("sensitive-token-leak")

    tracking_mod = ModuleType("mlflow.tracking")
    tracking_mod.MlflowClient = BrokenClient
    entities_mod = ModuleType("mlflow.entities")
    entities_mod.Metric = lambda *args: args
    entities_mod.Param = lambda *args: args
    monkeypatch.setitem(sys.modules, "mlflow.tracking", tracking_mod)
    monkeypatch.setitem(sys.modules, "mlflow.entities", entities_mod)
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://control-plane:8000/api/2.0/mlflow")

    trainer.main([])
    assert calls == ["http://control-plane:8000"]
    assert (root.parent / "model" / "model.joblib").is_file()
    report = json.loads((root.parent / "output" / "training_report.json").read_text())
    assert report["tracking_warning"] is not None
