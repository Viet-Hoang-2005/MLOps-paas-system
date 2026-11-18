import json
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
from src import application as app


@pytest.mark.parametrize(
    ("size", "methods", "threshold", "scores"),
    [
        (400, ["K-S p_value"] * 2 + ["Z-test p_value"] * 2, 0.05, [1.0635896769518578e-239, 1, 1, 0]),
        (
            1200,
            ["Wasserstein distance (normed)"] * 2 + ["Jensen-Shannon distance"] * 2,
            0.1,
            [6.034219578867654, 0, 0, 0.46450140402245904],
        ),
    ],
)
def test_new_report_matches_legacy_fixture(monkeypatch, tmp_path, size, methods, threshold, scores):
    rng = np.random.default_rng(1)
    reference = pd.DataFrame(
        {
            "a": rng.normal(size=size),
            "b": rng.normal(size=size),
            "cat": ["a", "b"] * (size // 2),
            "prediction": [0, 1] * (size // 2),
        }
    )
    production = reference.assign(a=reference.a + 6, prediction="1")
    monkeypatch.setattr(app, "TEMP_ROOT", tmp_path)
    monkeypatch.setattr(app, "HTML_UPLOAD_URL", "")
    monkeypatch.setattr(app, "DRIFT_THRESHOLD", 1 / 3)
    summary = app.run_drift_analysis(reference, production, app.get_data_definition(reference))
    assert summary["drifted_feature_names"] == ["a"]
    assert summary["prediction_drift"] is True
    assert summary["dataset_drift"] is True

    artifacts = summary["report_artifacts"]
    assert "<html" in Path(artifacts["local_html_path"]).read_text(encoding="utf-8").lower()
    report = json.loads(Path(artifacts["local_report_json_path"]).read_text(encoding="utf-8"))
    assert report["schema_version"] == 2
    columns = report["columns"]
    assert [col["column_name"] for col in columns] == ["a", "b", "cat", "prediction"]
    assert [col["stattest_name"] for col in columns] == methods
    assert [col["stattest_threshold"] for col in columns] == [threshold] * 4
    assert [col["drift_score"] for col in columns] == pytest.approx(scores)
    assert [col["drift_detected"] for col in columns] == [True, False, False, True]
    assert columns[0]["current"]["small_distribution"]["x"] == columns[0]["reference"]["small_distribution"]["x"]
    assert columns[2]["current"]["small_distribution"]["y"] == [size // 2] * 2


def test_all_features_missing_still_publishes_schema_alert(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "TEMP_ROOT", tmp_path)
    monkeypatch.setattr(app, "HTML_UPLOAD_URL", "")
    reference = pd.DataFrame({"a": [1.0, 2.0]})
    production = pd.DataFrame({"x": [2.0, 3.0]})
    summary = app.run_drift_analysis(reference, production, app.get_data_definition(reference))
    assert summary["dataset_drift"] is True
    assert summary["drifted_feature_names"] == ["a"]
    assert summary["data_quality"]["common_features_count"] == 0
    artifacts = summary["report_artifacts"]
    assert "Schema mismatch" in Path(artifacts["local_html_path"]).read_text(encoding="utf-8")
    assert json.loads(Path(artifacts["local_report_json_path"]).read_text(encoding="utf-8"))["columns"] == []


def test_missing_engine_result_fails_before_publishing(monkeypatch):
    snapshot = Mock(metric_results={})
    snapshot.dict.return_value = {"metrics": []}
    monkeypatch.setattr(app.analysis, "Report", Mock(return_value=Mock(run=Mock(return_value=snapshot))))
    save = Mock()
    monkeypatch.setattr(app, "save_drift_report", save)
    frame = pd.DataFrame({"a": [1.0, 2.0]})
    with pytest.raises(ValueError, match="Evidently returned no metrics for a"):
        app.run_drift_analysis(frame, frame, app.get_data_definition(frame))
    save.assert_not_called()
