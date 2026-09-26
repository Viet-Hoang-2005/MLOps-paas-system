#!/usr/bin/env python3
"""Multi-seed multi-level offline NIDS drift/retraining recovery evaluation.

Runs the 9-scenario evaluation across multiple random seeds and reports
mean +/- std for each metric. Produces a statistically rigorous Table 3.
"""

from __future__ import annotations

import hashlib
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
from sklearn.metrics import accuracy_score, f1_score
from xgboost import XGBClassifier

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

LABEL_COL = "Label"
CLASS_NAMES = ["BENIGN", "ATTACK"]
CLASS_TO_ID = {"BENIGN": 0, "ATTACK": 1}
BENIGN_ALIASES = {"BENIGN", "Benign", "benign", "Normal", "NORMAL", "normal"}

SEEDS = [42, 123, 456, 789, 1024]
MAX_TRAIN_ROWS = 100_000
MAX_WINDOW_ROWS = 50_000
ATTACK_TRIGGER_FRACTION = 0.60
PVALUE_THRESHOLD = 0.05
DRIFT_THRESHOLD = 0.30

LEVELS = [
    ("Mild",     0.15),
    ("Moderate", 0.40),
    ("Severe",   0.85),
]

ATTACK_SOURCES = [
    ("PortScan",    "drift_portscan.csv"),
    ("BruteForce",  "drift_bruteforce.csv"),
    ("WebAttacks",  "drift_webattacks.csv"),
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def output_dir() -> Path:
    return Path(__file__).resolve().parent / "multiseed"


def normalize_label(value: Any) -> str:
    return "BENIGN" if str(value).strip() in BENIGN_ALIASES else "ATTACK"


def load_csv(path: Path, max_rows: int, seed: int) -> pd.DataFrame:
    df = pd.read_csv(path)
    if max_rows > 0 and len(df) > max_rows:
        df = df.sample(n=max_rows, random_state=seed).sort_index().reset_index(drop=True)
    return df.reset_index(drop=True)


def feature_columns(df: pd.DataFrame) -> List[str]:
    return [c for c in df.columns if c != LABEL_COL]


def coerce_features(df: pd.DataFrame, cols: Sequence[str]) -> pd.DataFrame:
    X = df.loc[:, list(cols)].apply(pd.to_numeric, errors="coerce")
    return X.replace([np.inf, -np.inf], np.nan)


def apply_medians(X: pd.DataFrame, medians: pd.Series) -> pd.DataFrame:
    return X.fillna(medians).fillna(0.0)


def row_hash_list(df: pd.DataFrame, cols: Sequence[str]) -> List[str]:
    normalized = coerce_features(df, cols)
    normalized["__binary_label__"] = [normalize_label(v) for v in df[LABEL_COL].tolist()]
    hashed = pd.util.hash_pandas_object(normalized, index=False).astype("uint64")
    return [hashlib.sha256(str(int(v)).encode()).hexdigest() for v in hashed.to_numpy()]


def filter_by_label(df: pd.DataFrame, label: str) -> pd.DataFrame:
    mask = [normalize_label(v) == label for v in df[LABEL_COL].tolist()]
    return df.loc[mask].reset_index(drop=True)


def decontaminate(df: pd.DataFrame, cols: Sequence[str], blocked: set) -> pd.DataFrame:
    hashes = row_hash_list(df, cols)
    keep = [h not in blocked for h in hashes]
    return df.loc[keep].reset_index(drop=True)


def train_model(X: pd.DataFrame, y: np.ndarray, seed: int) -> XGBClassifier:
    counts = np.bincount(y, minlength=2)
    model = XGBClassifier(
        objective="binary:logistic", eval_metric="logloss",
        n_estimators=160, max_depth=6, learning_rate=0.08,
        subsample=0.9, colsample_bytree=0.9, min_child_weight=1,
        reg_lambda=1.0, random_state=seed, n_jobs=1, tree_method="hist",
        scale_pos_weight=float(counts[0] / counts[1]) if counts[1] else 1.0,
    )
    model.fit(X, y)
    return model


def evaluate_model(model, X, y):
    pred = np.asarray(model.predict(X), dtype=np.int64)
    return {
        "accuracy": float(accuracy_score(y, pred)),
        "macro_f1": float(f1_score(y, pred, average="macro", zero_division=0)),
    }


def compute_drift_stats(ref_X: pd.DataFrame, cur_X: pd.DataFrame):
    ks_stats = []
    drifted = 0
    for feat in ref_X.columns:
        r = ref_X[feat].dropna().to_numpy()
        c = cur_X[feat].dropna().to_numpy()
        if r.size == 0 or c.size == 0:
            ks_stats.append(0.0)
            continue
        result = ks_2samp(r, c, alternative="two-sided", mode="auto")
        ks_stats.append(float(result.statistic))
        if result.pvalue < PVALUE_THRESHOLD:
            drifted += 1
    return float(np.mean(ks_stats)), drifted, len(ref_X.columns)


def run_single_seed(seed: int, data_dir: Path) -> List[Dict[str, Any]]:
    """Run the full 9-scenario evaluation for one seed. Returns list of 9 result dicts."""
    train_raw = load_csv(data_dir / "train_2_classes.csv", MAX_TRAIN_ROWS, seed)
    reference_raw = load_csv(data_dir / "reference_data.csv", MAX_WINDOW_ROWS, seed)
    cols = feature_columns(train_raw)

    ref_benign = filter_by_label(reference_raw, "BENIGN")
    ref_benign = ref_benign.sample(frac=1.0, random_state=seed).reset_index(drop=True)

    # Collect attack data and future hashes
    attack_data = {}
    all_future_hashes: set = set()
    for i, (family, filename) in enumerate(ATTACK_SOURCES):
        attack_raw = load_csv(data_dir / filename, MAX_WINDOW_ROWS, seed + i + 10)
        attack_only = filter_by_label(attack_raw, "ATTACK")
        attack_only = attack_only.sample(frac=1.0, random_state=seed + i).reset_index(drop=True)
        n_trigger = min(max(1, int(len(attack_only) * ATTACK_TRIGGER_FRACTION)), len(attack_only) - 1)
        trigger_atk = attack_only.iloc[:n_trigger].reset_index(drop=True)
        future_atk = attack_only.iloc[n_trigger:].reset_index(drop=True)
        attack_data[family] = {"trigger": trigger_atk, "future": future_atk}
        all_future_hashes.update(set(row_hash_list(future_atk, cols)))

    # Train M0
    train_clean = decontaminate(train_raw, cols, all_future_hashes)
    medians = coerce_features(train_clean, cols).median(numeric_only=True).fillna(0.0)
    X_m0 = apply_medians(coerce_features(train_clean, cols), medians)
    y_m0 = np.array([CLASS_TO_ID[normalize_label(v)] for v in train_clean[LABEL_COL]], dtype=np.int64)
    model_m0 = train_model(X_m0, y_m0, seed)

    ref_X = apply_medians(coerce_features(ref_benign, cols), medians)

    results = []
    for fi, (family, _) in enumerate(ATTACK_SOURCES):
        trigger_atk = attack_data[family]["trigger"]
        future_atk = attack_data[family]["future"]
        future_hashes = set(row_hash_list(future_atk, cols))

        # Train M1
        m1_df = pd.concat([train_clean, trigger_atk], ignore_index=True)
        m1_df = decontaminate(m1_df, cols, future_hashes)
        X_m1 = apply_medians(coerce_features(m1_df, cols), medians)
        y_m1 = np.array([CLASS_TO_ID[normalize_label(v)] for v in m1_df[LABEL_COL]], dtype=np.int64)
        model_m1 = train_model(X_m1, y_m1, seed + fi + 500)

        for level_name, atk_fraction in LEVELS:
            n_atk_use = min(len(future_atk), 5000)
            if atk_fraction < 0.99:
                n_benign_use = min(int(round(n_atk_use * (1.0 - atk_fraction) / max(atk_fraction, 1e-9))), len(ref_benign))
            else:
                n_benign_use = 0

            atk_sample = future_atk.sample(n=n_atk_use, random_state=seed + fi * 10 + hash(level_name) % 100).reset_index(drop=True)
            if n_benign_use > 0:
                benign_sample = ref_benign.sample(n=n_benign_use, random_state=seed + fi * 10 + hash(level_name) % 200 + 1).reset_index(drop=True)
                window_df = pd.concat([atk_sample, benign_sample], ignore_index=True)
            else:
                window_df = atk_sample
            window_df = window_df.sample(frac=1.0, random_state=seed + fi * 10 + hash(level_name) % 300 + 2).reset_index(drop=True)

            window_labels = [normalize_label(v) for v in window_df[LABEL_COL]]
            actual_atk_pct = sum(1 for l in window_labels if l == "ATTACK") / len(window_labels)

            window_X = apply_medians(coerce_features(window_df, cols), medians)
            window_y = np.array([CLASS_TO_ID[l] for l in window_labels], dtype=np.int64)

            mean_ks, drifted_count, total_feats = compute_drift_stats(ref_X, window_X)
            drift_share = drifted_count / total_feats if total_feats > 0 else 0.0

            m0_eval = evaluate_model(model_m0, window_X, window_y)
            m1_eval = evaluate_model(model_m1, window_X, window_y)

            results.append({
                "seed": seed,
                "family": family,
                "level": level_name,
                "atk_pct": actual_atk_pct,
                "mean_ks": mean_ks,
                "drifted_features": drifted_count,
                "drift_share": drift_share,
                "fixed_mf1": m0_eval["macro_f1"],
                "chall_mf1": m1_eval["macro_f1"],
                "delta_mf1": m1_eval["macro_f1"] - m0_eval["macro_f1"],
            })
    return results


def main():
    root = repo_root()
    data_dir = root / "data"
    out = output_dir()
    out.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("Multi-Seed Multi-Level Evaluation")
    print(f"Seeds: {SEEDS}")
    print("=" * 70)

    all_results = []
    for i, seed in enumerate(SEEDS):
        print(f"\n--- Seed {seed} ({i+1}/{len(SEEDS)}) ---")
        seed_results = run_single_seed(seed, data_dir)
        all_results.extend(seed_results)
        # Print quick summary
        for r in seed_results:
            if r["level"] == "Severe":
                print(f"  {r['family']:>10s} Severe: KS={r['mean_ks']:.3f}  "
                      f"M0={r['fixed_mf1']:.3f}  M1={r['chall_mf1']:.3f}  "
                      f"D={r['delta_mf1']:+.3f}")

    # Aggregate
    df = pd.DataFrame(all_results)
    df.to_csv(out / "all_seed_results.csv", index=False, float_format="%.6f")

    # Group by (family, level) and compute mean +/- std
    agg = df.groupby(["family", "level"]).agg(
        atk_pct_mean=("atk_pct", "mean"),
        mean_ks_mean=("mean_ks", "mean"),
        mean_ks_std=("mean_ks", "std"),
        fixed_mf1_mean=("fixed_mf1", "mean"),
        fixed_mf1_std=("fixed_mf1", "std"),
        chall_mf1_mean=("chall_mf1", "mean"),
        chall_mf1_std=("chall_mf1", "std"),
        delta_mf1_mean=("delta_mf1", "mean"),
        delta_mf1_std=("delta_mf1", "std"),
        n_runs=("seed", "count"),
    ).reset_index()

    # Reorder levels
    level_order = {"Mild": 0, "Moderate": 1, "Severe": 2}
    family_order = {"PortScan": 0, "BruteForce": 1, "WebAttacks": 2}
    agg["_lo"] = agg["level"].map(level_order)
    agg["_fo"] = agg["family"].map(family_order)
    agg = agg.sort_values(["_fo", "_lo"]).drop(columns=["_lo", "_fo"]).reset_index(drop=True)

    agg.to_csv(out / "aggregated_results.csv", index=False, float_format="%.6f")

    # Print table
    print("\n" + "=" * 90)
    print(f"AGGREGATED RESULTS (n={len(SEEDS)} seeds)")
    print("=" * 90)
    print(f"{'Family':>10s} {'Level':>8s} {'Atk%':>5s} {'Mean KS':>14s} "
          f"{'Fixed M-F1':>14s} {'Chall M-F1':>14s} {'Delta M-F1':>14s}")
    print("-" * 90)
    for _, row in agg.iterrows():
        print(f"{row['family']:>10s} {row['level']:>8s} "
              f"{row['atk_pct_mean']:>4.0%} "
              f"{row['mean_ks_mean']:.3f}+/-{row['mean_ks_std']:.3f} "
              f"{row['fixed_mf1_mean']:.3f}+/-{row['fixed_mf1_std']:.3f} "
              f"{row['chall_mf1_mean']:.3f}+/-{row['chall_mf1_std']:.3f} "
              f"{row['delta_mf1_mean']:+.3f}+/-{row['delta_mf1_std']:.3f}")

    # Generate LaTeX table with mean +/- std
    print("\n" + "=" * 90)
    print("LaTeX TABLE (for paper)")
    print("=" * 90)
    latex_lines = []
    current_family = None
    families_list = list(agg["family"].unique())
    for idx, row in agg.iterrows():
        if row["family"] != current_family:
            if current_family is not None:
                latex_lines.append("\\midrule")
            current_family = row["family"]
            family_label = f"\\multirow{{3}}{{*}}{{{current_family}}}"
        else:
            family_label = ""

        atk_pct = f"{int(round(row['atk_pct_mean']*100))}\\%"
        mean_ks = f"{row['mean_ks_mean']:.3f}$\\pm${row['mean_ks_std']:.3f}"
        fixed = f"{row['fixed_mf1_mean']:.3f}$\\pm${row['fixed_mf1_std']:.3f}"
        chall = f"{row['chall_mf1_mean']:.3f}$\\pm${row['chall_mf1_std']:.3f}"
        delta = f"+{row['delta_mf1_mean']:.3f}"

        line = f"{family_label}\n  & {row['level']:<8s} & {atk_pct:<5s} & {mean_ks} & {fixed} & {chall} & {delta} \\\\"
        latex_lines.append(line)

    latex_output = "\n".join(latex_lines)
    (out / "multiseed_table_latex.txt").write_text(latex_output, encoding="utf-8")
    print(latex_output)

    # Summary JSON
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seeds": SEEDS,
        "n_seeds": len(SEEDS),
        "total_evaluations": len(all_results),
        "config": {
            "max_train_rows": MAX_TRAIN_ROWS,
            "max_window_rows": MAX_WINDOW_ROWS,
            "attack_trigger_fraction": ATTACK_TRIGGER_FRACTION,
            "pvalue_threshold": PVALUE_THRESHOLD,
            "drift_threshold": DRIFT_THRESHOLD,
            "levels": {name: frac for name, frac in LEVELS},
        },
    }
    (out / "multiseed_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\nDone! Results in: {out.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
