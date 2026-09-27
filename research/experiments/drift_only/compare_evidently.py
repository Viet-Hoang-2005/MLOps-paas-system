"""Replay frozen NIDS windows through Evidently's real DataDriftPreset.

This checks the detector adapter, not serving, ingestion, callbacks or retraining.
The frozen baseline and its source CSV are read-only. Results go to a new folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

import evidently
import pandas as pd
from evidently.metric_preset import DataDriftPreset
from evidently.pipeline.column_mapping import ColumnMapping
from evidently.report import Report


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASELINE = HERE / "results" / "run_20260926"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def run(output: Path, limit: int | None = None) -> None:
    started = time.monotonic()
    config = json.loads((BASELINE / "config.json").read_text(encoding="utf-8"))
    dataset = json.loads((BASELINE / "dataset_manifest.json").read_text(encoding="utf-8"))
    model = json.loads((BASELINE / "model_manifest.json").read_text(encoding="utf-8"))
    source = ROOT / config["source"]
    if sha256(source) != dataset["source_sha256"]:
        raise ValueError("Source CSV does not match the frozen baseline checksum")

    columns = model["features"]
    raw = pd.read_csv(source, usecols=columns)
    if len(raw) != dataset["raw_rows"] or raw[columns].isna().any().any():
        raise ValueError("Source rows/features differ from the frozen manifest")
    reference_ids = pd.read_csv(BASELINE / "reference_manifest.csv")["row_id"].to_numpy()
    reference = raw.iloc[reference_ids][columns].reset_index(drop=True)
    membership = pd.read_csv(BASELINE / "window_membership.csv.gz")
    metrics = pd.read_csv(BASELINE / "window_metrics.csv")
    if limit is not None:
        metrics = metrics.head(limit)
    groups = membership.groupby("window_id", sort=False)["row_id"]

    mapping = ColumnMapping()
    mapping.numerical_features = list(columns)
    output.mkdir(parents=True, exist_ok=False)
    rows: list[dict] = []
    feature_rows: list[dict] = []
    for index, baseline in enumerate(metrics.itertuples(index=False), start=1):
        row_ids = groups.get_group(baseline.window_id).to_numpy()
        if len(row_ids) != baseline.n:
            raise ValueError(f"Membership count mismatch for {baseline.window_id}")
        current = raw.iloc[row_ids][columns].reset_index(drop=True)

        # The deployed service uses DataDriftPreset(drift_share=DRIFT_THRESHOLD),
        # then counts drift_by_columns itself. It does not apply KS + BH.
        report = Report(metrics=[DataDriftPreset(drift_share=0.6)])
        report.run(reference_data=reference, current_data=current, column_mapping=mapping)
        report_data = report.as_dict()
        drift_columns = next(
            (item["result"]["drift_by_columns"] for item in report_data["metrics"]
             if "drift_by_columns" in item.get("result", {})),
            None,
        )
        if not isinstance(drift_columns, dict) or set(drift_columns) != set(columns):
            raise ValueError(f"Evidently feature list mismatch for {baseline.window_id}")
        count = sum(bool(item.get("drift_detected", False)) for item in drift_columns.values())
        share = count / len(columns)
        rows.append({
            "window_id": baseline.window_id,
            "scenario": baseline.scenario,
            "seed": baseline.seed,
            "n": baseline.n,
            "attack_recall": baseline.attack_recall,
            "macro_f1": baseline.macro_f1,
            "ks_bh_share": baseline.drift_share,
            "evidently_share": share,
            "evidently_drifted_features": count,
            "ks_bh_alert_030": int(baseline.drift_share >= 0.3),
            "evidently_alert_030": int(share >= 0.3),
            "ks_bh_alert_060": int(baseline.drift_share >= 0.6),
            "evidently_alert_060": int(share >= 0.6),
        })
        for feature, item in drift_columns.items():
            feature_rows.append({
                "window_id": baseline.window_id,
                "feature": feature,
                "drift_detected": bool(item.get("drift_detected", False)),
                "stattest_name": item.get("stattest_name", ""),
                "stattest_threshold": item.get("stattest_threshold", ""),
                "drift_score": item.get("drift_score", ""),
            })
        if index % 10 == 0 or index == len(metrics):
            print(f"{index}/{len(metrics)} windows", flush=True)

    windows = pd.DataFrame(rows)
    windows.to_csv(output / "window_comparison.csv", index=False)
    pd.DataFrame(feature_rows).to_csv(output / "feature_comparison.csv", index=False)
    summary = windows.groupby(["scenario", "n"], sort=False).agg(
        windows=("window_id", "size"),
        mean_recall=("attack_recall", "mean"),
        mean_evidently_share=("evidently_share", "mean"),
        ks_bh_alerts_030=("ks_bh_alert_030", "sum"),
        evidently_alerts_030=("evidently_alert_030", "sum"),
        ks_bh_alerts_060=("ks_bh_alert_060", "sum"),
        evidently_alerts_060=("evidently_alert_060", "sum"),
    ).reset_index()
    summary.to_csv(output / "scenario_comparison.csv", index=False)
    write_json(output / "manifest.json", {
        "baseline": str(BASELINE.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": dataset["source_sha256"],
        "model_sha256": model["model_sha256"],
        "baseline_membership_sha256": sha256(BASELINE / "window_membership.csv.gz"),
        "script_sha256": sha256(Path(__file__)),
        "python": platform.python_version(),
        "evidently": evidently.__version__,
        "pandas": pd.__version__,
        "configured_service_evidently": "0.4.15",
        "service_default_threshold": 0.6,
        "exploratory_threshold": 0.3,
        "windows": len(windows),
        "feature_comparisons": len(feature_rows),
        "seconds": round(time.monotonic() - started, 2),
        "scope": "Direct Evidently DataDriftPreset replay on frozen windows; no service, database, broker or callback",
    })
    print(summary.to_string(index=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=None, help="Pilot only; omit for all 120 windows")
    args = parser.parse_args()
    run(args.output, args.limit)
