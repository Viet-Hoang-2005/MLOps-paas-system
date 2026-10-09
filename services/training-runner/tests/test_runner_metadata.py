import json

import pytest
from src import application as runner


def test_training_artifacts_require_presigned_http_urls():
    runner.validate_presigned_url("https://bucket.example/object?signature=example")
    with pytest.raises(RuntimeError, match="presigned HTTP"):
        runner.validate_presigned_url("s3://bucket/input/source.zip")


def test_mlflow_artifact_uri_is_proxied_through_tracking_server():
    uri = runner.mlflow_proxy_artifact_uri("s3://bucket/users/tenant/job/mlflow/")
    assert uri == "mlflow-artifacts:/users/tenant/job/mlflow/"


def test_mlflow_artifact_uri_requires_s3_location():
    with pytest.raises(RuntimeError, match="Invalid S3 URI"):
        runner.mlflow_proxy_artifact_uri("https://example.test/artifacts")


def test_metric_parsing_normalizes_values_and_warnings():
    warnings = []
    events, metrics = runner.parse_metric_events(
        "\n".join(
            (
                'METRIC_JSON:{"accuracy":0.9,"flag":true,"tags":[1,{}]}',
                "METRIC_JSON:not-json",
                "METRIC_JSON:[1,2]",
            )
        ),
        warnings,
    )
    assert metrics == {"accuracy": 0.9}
    assert len(events) == 1
    assert {item["code"] for item in warnings} == {
        "invalid_metric_json",
        "invalid_metric_json_shape",
    }


def test_json_reading_and_metric_splitting(tmp_path):
    warnings = []
    assert runner.read_json_object(tmp_path / "missing.json", "metrics", warnings) == {}
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not-json", encoding="utf-8")
    assert runner.read_json_object(invalid, "metrics", warnings) == {}
    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    assert runner.read_json_object(array, "params", warnings) == {}
    metrics = runner.split_numeric_metrics({"loss": 0.2, "enabled": True, "note": "x"}, warnings, "file")
    assert metrics == {"loss": 0.2}
    assert any(item["code"] == "non_numeric_metric_ignored" for item in warnings)


@pytest.mark.parametrize(
    ("payload", "kind", "first"),
    [
        ({"feature_importance": {"a": 0.2, "b": -0.8}}, "feature_importance", "b"),
        ({"coefficients": {"a": -2, "b": 1}}, "coefficients", "a"),
        ({"items": [{"feature": "x", "importance": 3, "class": 1}]}, "weights", "x"),
    ],
)
def test_normalize_model_insights(payload, kind, first):
    result = runner.normalize_model_insights(payload, kind)
    assert result["kind"] == kind
    assert result["items"][0]["name"] == first
    assert result["items"][0]["rank"] == 1


def test_read_model_insights_rejects_invalid_content(tmp_path):
    warnings = []
    (tmp_path / "model_insights.json").write_text("not-json", encoding="utf-8")
    assert runner.read_model_insights(tmp_path, warnings) == {}
    assert warnings[0]["code"] == "invalid_model_insights_json"


def test_writes_mlops_bundle_and_manifest(runner_workspace):
    model_dir = runner_workspace["MODEL_DIR"]
    output_dir = runner_workspace["OUTPUT_DIR"]
    (model_dir / "model.pkl").write_bytes(b"demo-model")
    (output_dir / "metrics.json").write_text(
        json.dumps({"accuracy": 0.99, "loss": 0.05, "note": "ignored"}),
        encoding="utf-8",
    )
    (output_dir / "params.json").write_text(
        json.dumps({"n_estimators": 10, "nested": {"enabled": True}}), encoding="utf-8"
    )
    (output_dir / "feature_importance.json").write_text(
        json.dumps({"feature_importance": {"duration": 0.25, "packet_rate": 0.75}}),
        encoding="utf-8",
    )
    stdout = "\n".join(
        (
            "starting",
            'METRIC_JSON:{"accuracy":0.1,"precision":0.8}',
            "METRIC_JSON:not-json",
        )
    )

    runner.write_mlops_bundle(
        entry_point="train.py",
        model_version="v1",
        training_job_id="job-1",
        status="succeeded",
        stdout_text=stdout,
        stderr_text="warning",
    )

    mlops_dir = model_dir / "_mlops"
    metrics = json.loads((mlops_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics == {"accuracy": 0.99, "loss": 0.05, "precision": 0.8}
    insights = json.loads((mlops_dir / "model_insights.json").read_text(encoding="utf-8"))
    assert insights["items"][0]["name"] == "packet_rate"
    manifest = json.loads((mlops_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
    model_entry = next(item for item in manifest if item["path"] == "model.pkl")
    assert model_entry["kind"] == "model"
    assert len(model_entry["sha256"]) == 64
    summary = json.loads((mlops_dir / "training_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "succeeded"
    assert summary["warnings_count"] >= 2


def test_metric_parsing_supports_both_space_and_colon_prefixes():
    warnings = []
    events, metrics = runner.parse_metric_events(
        "\n".join(
            (
                'METRIC_JSON {"loss": 0.05, "step": 1}',
                'METRIC_JSON:{"accuracy": 0.95, "epoch": 2}',
                'METRIC_JSON: {"f1_score": 0.88}',
            )
        ),
        warnings,
    )
    assert metrics == {"loss": 0.05, "step": 1, "accuracy": 0.95, "epoch": 2, "f1_score": 0.88}
    assert len(events) == 3
    assert len(warnings) == 0


def _strict_json(path):
    """Parse like the Control Plane does: NaN/Infinity tokens are an error."""

    def refuse(token):
        raise ValueError(f"non-finite JSON constant {token}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=refuse)


def test_non_finite_metrics_never_reach_the_bundle(runner_workspace):
    model_dir = runner_workspace["MODEL_DIR"]
    output_dir = runner_workspace["OUTPUT_DIR"]
    (model_dir / "model.pkl").write_bytes(b"demo-model")
    # Python's json accepts these tokens, which is how a diverged loss reaches the file.
    (output_dir / "metrics.json").write_text('{"accuracy": 0.9, "loss": NaN, "grad": Infinity}', encoding="utf-8")
    (output_dir / "params.json").write_text('{"lr": 0.1, "init": -Infinity}', encoding="utf-8")
    (output_dir / "feature_importance.json").write_text(
        '{"feature_importance": {"a": NaN, "b": 0.5}}', encoding="utf-8"
    )
    runner.write_mlops_bundle(
        entry_point="train.py",
        model_version="v1",
        training_job_id="job-1",
        status="succeeded",
        stdout_text='METRIC_JSON {"val_loss": NaN, "val_acc": 0.8}',
        stderr_text="",
    )
    mlops_dir = model_dir / "_mlops"
    assert _strict_json(mlops_dir / "metrics.json") == {"accuracy": 0.9, "val_acc": 0.8}
    assert _strict_json(mlops_dir / "params.json") == {"lr": 0.1, "init": None}
    insights = _strict_json(mlops_dir / "model_insights.json")
    assert [item["name"] for item in insights["items"]] == ["b"]
    for name in ("warnings.json", "training_summary.json", "artifact_manifest.json"):
        _strict_json(mlops_dir / name)
    for line in (mlops_dir / "metric_events.jsonl").read_text(encoding="utf-8").splitlines():
        json.loads(line, parse_constant=lambda token: pytest.fail(f"non-finite {token}"))
    warnings = _strict_json(mlops_dir / "warnings.json")
    assert sum(item["count"] for item in warnings if item["code"] == "non_finite_value_ignored") >= 4


def test_metric_log_line_is_strict_json(monkeypatch):
    lines = []
    monkeypatch.setattr(runner.runtime_log, "protocol", lines.append)
    runner.metric_log({"loss": float("nan"), "acc": 0.5})
    assert "NaN" not in lines[0] and '"loss":null' in lines[0]
