#!/usr/bin/env python3
"""Multi-level offline NIDS drift/retraining recovery evaluation.

Produces a 9-row table: 3 attack families × 3 controlled attack fractions
(Mild ≈15%, Moderate ≈40%, Severe ≈85%).

For each attack family, M0 (fixed) and M1 (challenger) are trained once.
The evaluation/drift windows vary by level: ATTACK rows from the future-holdout
pool are mixed with BENIGN rows from the reference pool at the target fraction.

Output: paper/results/quantitative/multilevel/ directory with CSV and JSON.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
from sklearn.metrics import accuracy_score, f1_score, classification_report, confusion_matrix
from xgboost import XGBClassifier

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

LABEL_COL = "Label"
CLASS_NAMES = ["BENIGN", "ATTACK"]
CLASS_TO_ID = {"BENIGN": 0, "ATTACK": 1}
BENIGN_ALIASES = {"BENIGN", "Benign", "benign", "Normal", "NORMAL", "normal"}

SEED = 42
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
    return Path(__file__).resolve().parent / "multilevel"


def normalize_label(value: Any) -> str:
    text = str(value).strip()
    return "BENIGN" if text in BENIGN_ALIASES else "ATTACK"


def load_csv(path: Path, max_rows: int) -> pd.DataFrame:
    df = pd.read_csv(path)
    if max_rows > 0 and len(df) > max_rows:
        df = df.sample(n=max_rows, random_state=SEED).sort_index().reset_index(drop=True)
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


def train_model(X: pd.DataFrame, y: np.ndarray, seed: int, name: str) -> XGBClassifier:
    counts = np.bincount(y, minlength=2)
    model = XGBClassifier(
        objective="binary:logistic",
        eval_metric="logloss",
        n_estimators=160,
        max_depth=6,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        min_child_weight=1,
        reg_lambda=1.0,
        random_state=seed,
        n_jobs=1,
        tree_method="hist",
        scale_pos_weight=float(counts[0] / counts[1]) if counts[1] else 1.0,
    )
    model.fit(X, y)
    return model


def evaluate_model(model, X, y):
    pred = np.asarray(model.predict(X), dtype=np.int64)
    return {
        "accuracy": float(accuracy_score(y, pred)),
        "macro_f1": float(f1_score(y, pred, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y, pred, average="weighted", zero_division=0)),
    }


def compute_drift_stats(ref_X: pd.DataFrame, cur_X: pd.DataFrame):
    """Return (mean_ks, drifted_count, total_features)."""
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
    mean_ks = float(np.mean(ks_stats)) if ks_stats else 0.0
    return mean_ks, drifted, len(ref_X.columns)


def main():
    root = repo_root()
    data_dir = root / "data"
    out = output_dir()
    out.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("Multi-level Offline Drift/Retraining Recovery Evaluation")
    print("=" * 70)

    # ── Load base datasets ──
    print("\n[1/5] Loading datasets...")
    train_raw = load_csv(data_dir / "train_2_classes.csv", MAX_TRAIN_ROWS)
    reference_raw = load_csv(data_dir / "reference_data.csv", MAX_WINDOW_ROWS)
    cols = feature_columns(train_raw)
    print(f"  train_2_classes.csv: {len(train_raw)} rows, {len(cols)} features")
    print(f"  reference_data.csv:  {len(reference_raw)} rows (sampled to {MAX_WINDOW_ROWS})")

    # ── Split BENIGN pool from reference ──
    ref_benign = filter_by_label(reference_raw, "BENIGN")
    ref_benign = ref_benign.sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    print(f"  Reference BENIGN pool: {len(ref_benign)} rows")

    # ── Process each attack family ──
    results = []
    all_future_hashes: set = set()

    # First pass: collect all future hashes for M0 decontamination
    attack_data = {}
    for family, filename in ATTACK_SOURCES:
        attack_raw = load_csv(data_dir / filename, MAX_WINDOW_ROWS)
        attack_only = filter_by_label(attack_raw, "ATTACK")
        attack_only = attack_only.sample(frac=1.0, random_state=SEED).reset_index(drop=True)
        n_trigger = int(len(attack_only) * ATTACK_TRIGGER_FRACTION)
        n_trigger = min(max(1, n_trigger), len(attack_only) - 1)
        trigger_atk = attack_only.iloc[:n_trigger].reset_index(drop=True)
        future_atk = attack_only.iloc[n_trigger:].reset_index(drop=True)
        attack_data[family] = {
            "trigger": trigger_atk,
            "future": future_atk,
        }
        future_hashes = set(row_hash_list(future_atk, cols))
        all_future_hashes.update(future_hashes)
        print(f"  {family}: {len(attack_only)} ATTACK rows -> trigger={len(trigger_atk)}, future={len(future_atk)}")

    # ── Train M0 (fixed model) ──
    print("\n[2/5] Training fixed model M0...")
    train_clean = decontaminate(train_raw, cols, all_future_hashes)
    medians = coerce_features(train_clean, cols).median(numeric_only=True).fillna(0.0)
    X_m0 = apply_medians(coerce_features(train_clean, cols), medians)
    y_m0 = np.array([CLASS_TO_ID[normalize_label(v)] for v in train_clean[LABEL_COL]], dtype=np.int64)
    model_m0 = train_model(X_m0, y_m0, SEED, "M0-fixed")
    print(f"  M0 trained on {len(train_clean)} rows (BENIGN={int(np.sum(y_m0==0))}, ATTACK={int(np.sum(y_m0==1))})")

    # ── Reference baseline for drift (BENIGN only from reference pool) ──
    ref_X = apply_medians(coerce_features(ref_benign, cols), medians)

    # ── Per-family challenger + multi-level evaluation ──
    print("\n[3/5] Training challengers and evaluating 9 scenarios...")
    for family_idx, (family, filename) in enumerate(ATTACK_SOURCES):
        trigger_atk = attack_data[family]["trigger"]
        future_atk = attack_data[family]["future"]
        future_hashes = set(row_hash_list(future_atk, cols))

        # Train M1 (challenger) using M0 training data + trigger attack rows
        m1_train_df = pd.concat([train_clean, trigger_atk], ignore_index=True)
        m1_train_df = decontaminate(m1_train_df, cols, future_hashes)
        X_m1 = apply_medians(coerce_features(m1_train_df, cols), medians)
        y_m1 = np.array([CLASS_TO_ID[normalize_label(v)] for v in m1_train_df[LABEL_COL]], dtype=np.int64)
        model_m1 = train_model(X_m1, y_m1, SEED + family_idx + 500, f"M1-{family}")
        print(f"\n  [{family}] M1 trained on {len(m1_train_df)} rows "
              f"(BENIGN={int(np.sum(y_m1==0))}, ATTACK={int(np.sum(y_m1==1))})")

        for level_name, atk_fraction in LEVELS:
            # Build evaluation window: mix future_atk with ref_benign at target atk_fraction
            n_atk_available = len(future_atk)
            # Target: atk_fraction = n_atk / (n_atk + n_benign)
            # Compute how many BENIGN rows to mix for the target fraction
            if atk_fraction >= 0.99:
                n_atk_use = n_atk_available
                n_benign_use = 0
            else:
                # Use up to 5000 attack rows, scale benign accordingly
                n_atk_use = min(n_atk_available, 5000)
                n_benign_use = int(round(n_atk_use * (1.0 - atk_fraction) / max(atk_fraction, 1e-9)))
                n_benign_use = min(n_benign_use, len(ref_benign))
                # Recompute actual attack fraction
                if n_benign_use == 0:
                    n_atk_use = n_atk_available

            # Sample attack and benign rows
            if n_atk_use > n_atk_available:
                n_atk_use = n_atk_available
            atk_sample = future_atk.sample(n=n_atk_use, random_state=SEED + family_idx * 10 + hash(level_name) % 100).reset_index(drop=True)

            if n_benign_use > 0:
                benign_sample = ref_benign.sample(n=n_benign_use, random_state=SEED + family_idx * 10 + hash(level_name) % 200 + 1).reset_index(drop=True)
                window_df = pd.concat([atk_sample, benign_sample], ignore_index=True)
            else:
                window_df = atk_sample

            window_df = window_df.sample(frac=1.0, random_state=SEED + family_idx * 10 + hash(level_name) % 300 + 2).reset_index(drop=True)

            # Actual attack fraction
            window_labels = [normalize_label(v) for v in window_df[LABEL_COL]]
            actual_atk_count = sum(1 for l in window_labels if l == "ATTACK")
            actual_benign_count = len(window_labels) - actual_atk_count
            actual_atk_pct = actual_atk_count / len(window_labels) if len(window_labels) > 0 else 0

            # Prepare features
            window_X = apply_medians(coerce_features(window_df, cols), medians)
            window_y = np.array([CLASS_TO_ID[l] for l in window_labels], dtype=np.int64)

            # Compute drift (reference BENIGN vs this window)
            mean_ks, drifted_count, total_feats = compute_drift_stats(ref_X, window_X)
            drift_share = drifted_count / total_feats if total_feats > 0 else 0.0
            drift_detected = drift_share >= DRIFT_THRESHOLD

            # Evaluate M0 and M1 on this window
            m0_eval = evaluate_model(model_m0, window_X, window_y)
            m1_eval = evaluate_model(model_m1, window_X, window_y)
            delta_mf1 = m1_eval["macro_f1"] - m0_eval["macro_f1"]

            results.append({
                "Attack Family": family,
                "Level": level_name,
                "Atk%": f"{int(round(actual_atk_pct * 100))}%",
                "Atk% (numeric)": round(actual_atk_pct, 3),
                "Window Size": len(window_df),
                "ATTACK rows": actual_atk_count,
                "BENIGN rows": actual_benign_count,
                "Mean KS": round(mean_ks, 3),
                "Drifted Features": drifted_count,
                "Drift Share": round(drift_share, 3),
                "Drift Detected": drift_detected,
                "Fixed M-F1": round(m0_eval["macro_f1"], 3),
                "Chall. M-F1": round(m1_eval["macro_f1"], 3),
                "ΔM-F1": round(delta_mf1, 3),
                "Fixed Acc": round(m0_eval["accuracy"], 3),
                "Chall. Acc": round(m1_eval["accuracy"], 3),
            })

            print(f"    {level_name:>8s} | Atk={actual_atk_pct:.0%} ({actual_atk_count}/{len(window_df)}) | "
                  f"Mean KS={mean_ks:.3f} | Drift={drifted_count}/{total_feats} | "
                  f"M0 F1={m0_eval['macro_f1']:.3f} | M1 F1={m1_eval['macro_f1']:.3f} | "
                  f"Δ={delta_mf1:+.3f}")

    # ── Save results ──
    print("\n[4/5] Saving results...")
    results_df = pd.DataFrame(results)
    results_df.to_csv(out / "multilevel_results.csv", index=False)

    # LaTeX-friendly table for paper
    latex_rows = []
    for r in results:
        latex_rows.append(
            f"  & {r['Level']:<8s} & {r['Atk%']:<4s} & {r['Mean KS']:.3f} "
            f"& {r['Fixed M-F1']:.3f} & {r['Chall. M-F1']:.3f} & {r['ΔM-F1']:+.3f} \\\\"
        )

    # Group by family with \multirow
    latex_table = []
    families = [f for f, _ in ATTACK_SOURCES]
    for i, family in enumerate(families):
        family_rows = [r for r in latex_rows[i*3:(i+1)*3]]
        family_rows[0] = f"\\multirow{{3}}{{*}}{{{family}}}\n{family_rows[0]}"
        latex_table.extend(family_rows)
        if i < len(families) - 1:
            latex_table.append("\\midrule")

    latex_output = "\n".join(latex_table)
    (out / "multilevel_table_latex.txt").write_text(latex_output, encoding="utf-8")

    # Summary JSON
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "max_train_rows": MAX_TRAIN_ROWS,
        "max_window_rows": MAX_WINDOW_ROWS,
        "attack_trigger_fraction": ATTACK_TRIGGER_FRACTION,
        "pvalue_threshold": PVALUE_THRESHOLD,
        "drift_threshold": DRIFT_THRESHOLD,
        "levels": {name: frac for name, frac in LEVELS},
        "m0_training_rows": len(train_clean),
        "reference_benign_rows": len(ref_benign),
        "results": results,
    }
    (out / "multilevel_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\n[5/5] Done! Results in: {out.relative_to(root)}")
    print("\n" + "=" * 70)
    print("RESULTS TABLE (for paper Table 3)")
    print("=" * 70)
    print(results_df[["Attack Family", "Level", "Atk%", "Mean KS",
                       "Fixed M-F1", "Chall. M-F1", "ΔM-F1"]].to_string(index=False))
    print("\n" + "=" * 70)
    print("LaTeX table fragment saved to: multilevel_table_latex.txt")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
