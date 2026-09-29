"""Check completeness and aggregation of a saved Evidently replay."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(output: Path) -> dict:
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    baseline = ROOT / manifest["baseline"]
    baseline_config = json.loads((baseline / "config.json").read_text(encoding="utf-8"))
    baseline_model = json.loads((baseline / "model_manifest.json").read_text(encoding="utf-8"))
    assert sha256(ROOT / baseline_config["source"]) == manifest["source_sha256"]
    assert sha256(baseline / "window_membership.csv.gz") == manifest["baseline_membership_sha256"]
    assert baseline_model["model_sha256"] == manifest["model_sha256"]

    windows = pd.read_csv(output / "window_comparison.csv")
    features = pd.read_csv(output / "feature_comparison.csv")
    summary = pd.read_csv(output / "scenario_comparison.csv")
    original = pd.read_csv(baseline / "window_metrics.csv")
    assert len(windows) == len(original) == manifest["windows"] == 120
    assert windows.window_id.is_unique
    assert set(windows.window_id) == set(original.window_id)
    assert len(features) == manifest["feature_comparisons"] == len(windows) * 52
    assert features.groupby("window_id").feature.nunique().eq(52).all()
    assert set(features.feature) == set(baseline_model["features"])

    counts = features.groupby("window_id").drift_detected.sum()
    indexed = windows.set_index("window_id")
    assert indexed.evidently_drifted_features.eq(counts).all()
    assert (indexed.evidently_share - counts / 52).abs().max() < 1e-12
    for threshold, suffix in ((0.3, "030"), (0.6, "060")):
        assert indexed[f"evidently_alert_{suffix}"].eq(indexed.evidently_share >= threshold).all()
        assert indexed[f"ks_bh_alert_{suffix}"].eq(indexed.ks_bh_share >= threshold).all()
    aligned = indexed.loc[original.window_id]
    assert abs(aligned.ks_bh_share.to_numpy() - original.drift_share.to_numpy()).max() < 1e-12
    assert abs(aligned.attack_recall.to_numpy() - original.attack_recall.to_numpy()).max() < 1e-12
    for row in summary.itertuples(index=False):
        subset = windows[(windows.scenario == row.scenario) & (windows.n == row.n)]
        assert len(subset) == row.windows
        for name in ("ks_bh_alerts_030", "evidently_alerts_030", "ks_bh_alerts_060", "evidently_alerts_060"):
            assert getattr(row, name) == subset[name.replace("alerts", "alert")].sum()

    return {
        "status": "passed",
        "windows": len(windows),
        "feature_results": len(features),
        "checks": [
            "frozen source and membership checksums",
            "one-to-one window IDs with baseline metrics",
            "52 distinct expected features per window",
            "feature-level counts, shares and alert flags",
            "scenario-level alert totals",
        ],
        "limit": "Does not independently recompute Evidently's per-feature statistics or test end-to-end service behavior",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = verify(args.output)
    (args.output / "verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
