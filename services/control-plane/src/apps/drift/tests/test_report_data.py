import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from apps.drift.runs.reports import get_drift_report_data


def read_report(monkeypatch, report, summary):
    version = SimpleNamespace(version=1, project=SimpleNamespace(public_id=uuid4(), name="Test"))
    run = SimpleNamespace(
        public_id=uuid4(),
        monitor=SimpleNamespace(public_id=uuid4(), version=version),
        status="completed",
        created_at=None,
        summary=summary,
        report_html_uri="s3://test/report.html",
        report_json_uri="s3://test/report.json",
    )
    storage = Mock()
    storage.presigned_get.side_effect = lambda uri, _, **__: uri.replace("s3://", "https://")
    storage.read.return_value = json.dumps(report).encode("utf-8")
    monkeypatch.setattr("infrastructure.storage.S3Storage", lambda: storage)
    return get_drift_report_data(run)


def test_new_report_uses_effective_drift_from_summary(monkeypatch):
    column = {
        "column_name": "present",
        "column_type": "num",
        "stattest_name": "K-S p_value",
        "stattest_threshold": 0.05,
        "drift_score": 1.0,
        "drift_detected": False,
    }
    data = read_report(
        monkeypatch,
        {"schema_version": 2, "columns": [column], "evidently_metrics": []},
        {
            "dataset_drift": True,
            "drift_score": 0.5,
            "drift_threshold": 0.6,
            "number_of_features": 2,
            "number_of_drifted_features": 1,
        },
    )
    assert data["dataset_drift"] is True
    assert data["drift_score"] == 0.5
    assert data["drift_share"] == 0.6
    assert (data["number_of_columns"], data["number_of_drifted_columns"]) == (2, 1)
    assert data["columns"] == [column]
    assert data["artifacts"]["html_url"] == "https://test/report.html"


def test_legacy_report_retains_its_metrics_and_rows(monkeypatch):
    data = read_report(
        monkeypatch,
        {
            "metrics": [
                {
                    "metric": "DatasetDriftMetric",
                    "result": {
                        "dataset_drift": False,
                        "share_of_drifted_columns": 0.25,
                        "number_of_columns": 4,
                        "number_of_drifted_columns": 1,
                    },
                },
                {
                    "metric": "DataDriftTable",
                    "result": {"drift_by_columns": {"feature": {"drift_detected": True, "drift_score": 0.01}}},
                },
            ]
        },
        {"dataset_drift": True, "drift_score": 0.5},
    )
    assert data["dataset_drift"] is False
    assert data["drift_score"] == 0.25
    assert data["columns"][0]["column_name"] == "feature"
    assert data["columns"][0]["drift_detected"] is True
