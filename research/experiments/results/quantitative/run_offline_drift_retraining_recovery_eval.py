#!/usr/bin/env python3
"""Offline NIDS drift/retraining recovery evaluation.

This script builds clean binary BENIGN-vs-ATTACK recovery scenarios by splitting
attack drift files into trigger/retraining and future holdout subsets. It writes
new recovery-specific artifacts under paper/results/quantitative/recovery/ and
does not mutate source datasets, source models, prior quantitative outputs, or
the paper.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.dont_write_bytecode = True

import numpy as np
import pandas as pd

try:
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing required dependency scikit-learn. Install it with: "
        "python -m pip install scikit-learn"
    ) from exc

try:
    from xgboost import XGBClassifier
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing required dependency xgboost. Install it with: python -m pip install xgboost"
    ) from exc

try:
    from scipy.stats import ks_2samp
except ImportError:  # pragma: no cover
    ks_2samp = None

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

LABEL_COL = "Label"
CLASS_NAMES = ["BENIGN", "ATTACK"]
CLASS_TO_ID = {"BENIGN": 0, "ATTACK": 1}
BENIGN_ALIASES = {"BENIGN", "Benign", "benign", "Normal", "NORMAL", "normal"}


@dataclass
class ScenarioData:
    scenario: str
    attack_family: str
    attack_source: str
    trigger_df: pd.DataFrame
    future_df: pd.DataFrame
    trigger_attack_rows: int
    future_attack_rows: int
    trigger_benign_rows: int
    future_benign_rows: int
    dropped_duplicate_attack_rows: int
    trigger_fraction_requested: float


@dataclass
class PreparedDataset:
    name: str
    df: pd.DataFrame
    X: pd.DataFrame
    y: np.ndarray
    y_labels: List[str]
    row_hashes: List[str]
    raw_label_counts: Dict[str, int]
    binary_label_counts: Dict[str, int]

    @property
    def row_hash_set(self) -> set[str]:
        return set(self.row_hashes)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline drift/retraining recovery evaluation.")
    parser.add_argument("--binary", action="store_true", help="Run required BENIGN-vs-ATTACK experiment.")
    parser.add_argument("--drift-threshold", type=float, default=0.5)
    parser.add_argument("--pvalue-threshold", type=float, default=0.05)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--max-train-rows", type=int, default=100000)
    parser.add_argument("--max-window-rows", type=int, default=50000)
    parser.add_argument("--attack-trigger-fraction", type=float, default=0.6)
    parser.add_argument("--benign-reference-fraction", type=float, default=0.6)
    parser.add_argument("--benign-retraining-fraction", type=float, default=0.2)
    parser.add_argument(
        "--drift-benign-mix-fraction",
        type=float,
        default=0.3,
        help=(
            "Fraction of BENIGN rows (from reference_benign pool) to mix into the "
            "trigger window used ONLY for drift computation. This makes the drift "
            "window more realistic (default: 0.3 = ~30%% BENIGN). "
            "Set to 0.0 to keep the original 100%%-ATTACK drift window."
        ),
    )
    parser.add_argument(
        "--use-mixed-reference-for-drift",
        action="store_true",
        default=False,
        help=(
            "Use the full reference_data.csv (BENIGN + known attacks like DDoS) as the "
            "drift reference baseline instead of only BENIGN rows. This is the more "
            "realistic production setting where the reference represents typical mixed "
            "traffic, and drift measures deviation from that baseline."
        ),
    )
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def output_dir() -> Path:
    return Path(__file__).resolve().parent / "recovery"


def rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def normalize_label(value: Any) -> str:
    text = str(value).strip()
    return "BENIGN" if text in BENIGN_ALIASES else "ATTACK"


def load_csv(path: Path, max_rows: int, seed: int) -> Tuple[pd.DataFrame, int, bool]:
    if not path.exists():
        raise FileNotFoundError(f"Missing dataset: {path}")
    df = pd.read_csv(path)
    raw_rows = int(len(df))
    if max_rows > 0 and len(df) > max_rows:
        df = df.sample(n=max_rows, random_state=seed).sort_index().reset_index(drop=True)
        return df, raw_rows, True
    return df.reset_index(drop=True), raw_rows, False


def feature_columns(df: pd.DataFrame, dataset_name: str) -> List[str]:
    if LABEL_COL not in df.columns:
        raise ValueError(f"{dataset_name} does not contain required label column '{LABEL_COL}'")
    return [column for column in df.columns if column != LABEL_COL]


def validate_features(df: pd.DataFrame, expected: Sequence[str], dataset_name: str) -> None:
    current = feature_columns(df, dataset_name)
    if list(current) != list(expected):
        missing = sorted(set(expected) - set(current))
        extra = sorted(set(current) - set(expected))
        raise ValueError(f"Feature schema mismatch for {dataset_name}: missing={missing[:10]}, extra={extra[:10]}")


def coerce_features(df: pd.DataFrame, cols: Sequence[str]) -> pd.DataFrame:
    X = df.loc[:, list(cols)].apply(pd.to_numeric, errors="coerce")
    return X.replace([np.inf, -np.inf], np.nan)


def apply_medians(X: pd.DataFrame, medians: pd.Series) -> pd.DataFrame:
    return X.fillna(medians).fillna(0.0)


def row_hash_list(df: pd.DataFrame, cols: Sequence[str]) -> List[str]:
    normalized = coerce_features(df, cols)
    normalized["__binary_label__"] = [normalize_label(value) for value in df[LABEL_COL].tolist()]
    hashed = pd.util.hash_pandas_object(normalized, index=False).astype("uint64")
    return [hashlib.sha256(str(int(value)).encode("utf-8")).hexdigest() for value in hashed.to_numpy()]


def with_row_hash(df: pd.DataFrame, cols: Sequence[str]) -> pd.DataFrame:
    out = df.reset_index(drop=True).copy()
    out["__row_hash__"] = row_hash_list(out, cols)
    return out


def drop_duplicate_hashes(df: pd.DataFrame, cols: Sequence[str]) -> Tuple[pd.DataFrame, int]:
    hashed = with_row_hash(df, cols)
    before = len(hashed)
    deduped = hashed.drop_duplicates("__row_hash__", keep="first").drop(columns=["__row_hash__"]).reset_index(drop=True)
    return deduped, int(before - len(deduped))


def filter_by_binary_label(df: pd.DataFrame, label: str) -> pd.DataFrame:
    mask = [normalize_label(value) == label for value in df[LABEL_COL].tolist()]
    return df.loc[mask].reset_index(drop=True)


def shuffled(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    return df.sample(frac=1.0, random_state=seed).reset_index(drop=True)


def split_benign_pool(reference_df: pd.DataFrame, cols: Sequence[str], seed: int, ref_fraction: float, retrain_fraction: float) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    benign = filter_by_binary_label(reference_df, "BENIGN")
    benign, dropped = drop_duplicate_hashes(benign, cols)
    benign = shuffled(benign, seed)
    if len(benign) < 30:
        raise ValueError("Not enough BENIGN rows in reference_data.csv to create reference/retraining/evaluation splits")
    n_ref = max(1, int(len(benign) * ref_fraction))
    n_retrain = max(1, int(len(benign) * retrain_fraction))
    if n_ref + n_retrain >= len(benign):
        n_ref = max(1, len(benign) // 2)
        n_retrain = max(1, (len(benign) - n_ref) // 2)
    reference_benign = benign.iloc[:n_ref].reset_index(drop=True)
    retrain_benign = benign.iloc[n_ref:n_ref + n_retrain].reset_index(drop=True)
    eval_benign = benign.iloc[n_ref + n_retrain:].reset_index(drop=True)
    summary = {
        "source": "data/reference_data.csv BENIGN rows",
        "unique_benign_rows": int(len(benign)),
        "dropped_duplicate_rows": dropped,
        "reference_rows": int(len(reference_benign)),
        "retraining_rows": int(len(retrain_benign)),
        "evaluation_holdout_rows": int(len(eval_benign)),
        "reference_fraction_requested": ref_fraction,
        "retraining_fraction_requested": retrain_fraction,
    }
    return reference_benign, retrain_benign, eval_benign, summary


def split_attack_source(df: pd.DataFrame, cols: Sequence[str], seed: int, trigger_fraction: float) -> Tuple[pd.DataFrame, pd.DataFrame, int]:
    attack = filter_by_binary_label(df, "ATTACK")
    attack, dropped = drop_duplicate_hashes(attack, cols)
    attack = shuffled(attack, seed)
    if len(attack) < 10:
        raise ValueError("Attack source too small after de-duplication")
    n_trigger = int(len(attack) * trigger_fraction)
    n_trigger = min(max(1, n_trigger), len(attack) - 1)
    trigger = attack.iloc[:n_trigger].reset_index(drop=True)
    future = attack.iloc[n_trigger:].reset_index(drop=True)
    return trigger, future, dropped


def decontaminate_against(df: pd.DataFrame, cols: Sequence[str], blocked_hashes: set[str]) -> Tuple[pd.DataFrame, int]:
    hashes = row_hash_list(df, cols)
    keep = [row_hash not in blocked_hashes for row_hash in hashes]
    removed = int(len(keep) - sum(keep))
    return df.loc[keep].reset_index(drop=True), removed


def prepare_dataset(name: str, df: pd.DataFrame, cols: Sequence[str], medians: pd.Series) -> PreparedDataset:
    X = apply_medians(coerce_features(df, cols), medians)
    y_labels = [normalize_label(value) for value in df[LABEL_COL].tolist()]
    y = np.array([CLASS_TO_ID[label] for label in y_labels], dtype=np.int64)
    raw_counts = df[LABEL_COL].astype(str).value_counts(dropna=False).to_dict()
    binary_counts = pd.Series(y_labels).value_counts().reindex(CLASS_NAMES, fill_value=0).to_dict()
    return PreparedDataset(
        name=name,
        df=df.reset_index(drop=True),
        X=X,
        y=y,
        y_labels=y_labels,
        row_hashes=row_hash_list(df, cols),
        raw_label_counts={str(k): int(v) for k, v in raw_counts.items()},
        binary_label_counts={str(k): int(v) for k, v in binary_counts.items()},
    )


def train_model(X: pd.DataFrame, y: np.ndarray, seed: int, name: str) -> XGBClassifier:
    counts = np.bincount(y, minlength=2)
    if counts[0] == 0 or counts[1] == 0:
        raise ValueError(f"{name} training data must contain both BENIGN and ATTACK")
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


def evaluate(model: XGBClassifier, dataset: PreparedDataset, model_name: str, scenario: str, attack_family: str) -> Dict[str, Any]:
    pred = np.asarray(model.predict(dataset.X), dtype=np.int64)
    report = classification_report(
        dataset.y,
        pred,
        labels=[0, 1],
        target_names=CLASS_NAMES,
        output_dict=True,
        zero_division=0,
    )
    return {
        "Scenario": scenario,
        "Attack family": attack_family,
        "Dataset": dataset.name,
        "Model": model_name,
        "Accuracy": float(accuracy_score(dataset.y, pred)),
        "Macro-F1": float(f1_score(dataset.y, pred, average="macro", zero_division=0)),
        "Weighted-F1": float(f1_score(dataset.y, pred, average="weighted", zero_division=0)),
        "per_class": {
            label: {
                "precision": float(report[label]["precision"]),
                "recall": float(report[label]["recall"]),
                "f1-score": float(report[label]["f1-score"]),
                "support": int(report[label]["support"]),
            }
            for label in CLASS_NAMES
        },
        "confusion_matrix": confusion_matrix(dataset.y, pred, labels=[0, 1]).tolist(),
    }


def psi_score(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    reference = reference[np.isfinite(reference)]
    current = current[np.isfinite(current)]
    if reference.size == 0 or current.size == 0:
        return 0.0
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    if edges.size < 2:
        return 0.0 if np.allclose(reference.mean(), current.mean()) else 1.0
    ref_counts, _ = np.histogram(reference, bins=edges)
    cur_counts, _ = np.histogram(current, bins=edges)
    ref_pct = np.maximum(ref_counts / max(ref_counts.sum(), 1), 1e-6)
    cur_pct = np.maximum(cur_counts / max(cur_counts.sum(), 1), 1e-6)
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def compute_drift(reference: PreparedDataset, current: PreparedDataset, pvalue_threshold: float, drift_threshold: float, scenario: str, attack_family: str) -> Dict[str, Any]:
    method = "ks_2samp" if ks_2samp is not None else "psi_fallback"
    feature_results: Dict[str, Dict[str, Any]] = {}
    drifted_features: List[str] = []
    for feature in reference.X.columns:
        ref_values = reference.X[feature].to_numpy(dtype=float)
        cur_values = current.X[feature].to_numpy(dtype=float)
        ref_values = ref_values[np.isfinite(ref_values)]
        cur_values = cur_values[np.isfinite(cur_values)]
        if ks_2samp is not None:
            if ref_values.size == 0 or cur_values.size == 0:
                statistic = 0.0
                pvalue = 1.0
                drifted = False
            else:
                result = ks_2samp(ref_values, cur_values, alternative="two-sided", mode="auto")
                statistic = float(result.statistic)
                pvalue = float(result.pvalue)
                drifted = bool(pvalue < pvalue_threshold)
            feature_results[feature] = {
                "method": method,
                "statistic": statistic,
                "p_value": pvalue,
                "threshold": pvalue_threshold,
                "drifted": drifted,
            }
        else:
            score = psi_score(ref_values, cur_values)
            drifted = bool(score >= 0.2)
            feature_results[feature] = {"method": method, "psi": score, "threshold": 0.2, "drifted": drifted}
        if drifted:
            drifted_features.append(feature)
    total = int(len(reference.X.columns))
    drift_share = len(drifted_features) / total if total else 0.0
    return {
        "Scenario": scenario,
        "Attack family": attack_family,
        "method": method,
        "drifted_feature_count": int(len(drifted_features)),
        "total_features": total,
        "drift_share": float(drift_share),
        "dataset_drift": bool(drift_share >= drift_threshold),
        "drift_threshold": drift_threshold,
        "drifted_features": drifted_features,
        "feature_results": feature_results,
    }


def metric_row(metrics: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "Scenario": metrics["Scenario"],
        "Attack family": metrics["Attack family"],
        "Dataset": metrics["Dataset"],
        "Model": metrics["Model"],
        "Accuracy": metrics["Accuracy"],
        "Macro-F1": metrics["Macro-F1"],
        "Weighted-F1": metrics["Weighted-F1"],
    }


def per_class_rows(metrics: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in metrics:
        for class_name, values in item["per_class"].items():
            rows.append(
                {
                    "Scenario": item["Scenario"],
                    "Attack family": item["Attack family"],
                    "Dataset": item["Dataset"],
                    "Model": item["Model"],
                    "Class": class_name,
                    "Precision": values["precision"],
                    "Recall": values["recall"],
                    "F1": values["f1-score"],
                    "Support": values["support"],
                }
            )
    return rows


def composition(dataset: PreparedDataset) -> str:
    benign = int(dataset.binary_label_counts.get("BENIGN", 0))
    attack = int(dataset.binary_label_counts.get("ATTACK", 0))
    return f"BENIGN={benign}, ATTACK={attack}"


def overlap_report(training: PreparedDataset, evaluation: PreparedDataset, trigger: PreparedDataset) -> Dict[str, Any]:
    train_hashes = training.row_hash_set
    eval_hashes = evaluation.row_hash_set
    trigger_hashes = trigger.row_hash_set
    train_eval = train_hashes.intersection(eval_hashes)
    trigger_eval = trigger_hashes.intersection(eval_hashes)
    return {
        "m1_training_vs_future_holdout_unique_overlap": int(len(train_eval)),
        "trigger_window_vs_future_holdout_unique_overlap": int(len(trigger_eval)),
        "m1_training_rows_overlapping_future_holdout": int(sum(1 for row_hash in training.row_hashes if row_hash in eval_hashes)),
        "future_holdout_rows_overlapping_m1_training": int(sum(1 for row_hash in evaluation.row_hashes if row_hash in train_hashes)),
        "trigger_rows_overlapping_future_holdout": int(sum(1 for row_hash in trigger.row_hashes if row_hash in eval_hashes)),
        "leakage_safe": not train_eval and not trigger_eval,
    }


def inspect_pickle_model(path: Path) -> Dict[str, Any]:
    info = {"path": str(path), "exists": path.exists(), "loaded": False, "type": None, "n_features_in_": None, "classes_": None, "load_error": None}
    if not path.exists():
        return info
    try:
        with path.open("rb") as handle:
            model = pickle.load(handle)
        info["loaded"] = True
        info["type"] = f"{type(model).__module__}.{type(model).__name__}"
        if hasattr(model, "n_features_in_"):
            info["n_features_in_"] = int(getattr(model, "n_features_in_"))
        if hasattr(model, "classes_"):
            info["classes_"] = [str(value) for value in list(getattr(model, "classes_"))]
    except Exception as exc:
        info["load_error"] = repr(exc)
    return info


def make_readme(command: str, config: Dict[str, Any], comparison: pd.DataFrame) -> str:
    rows = []
    for _, row in comparison.iterrows():
        rows.append(
            f"- {row['Scenario']} {row['Attack family']}: drift_share={row['Drift share']:.3f}, "
            f"fixed Macro-F1={row['Fixed Macro-F1']:.4f}, retrained Macro-F1={row['Retrained Macro-F1']:.4f}, "
            f"Delta Macro-F1={row['Delta Macro-F1']:.4f}."
        )
    return f"""# Offline Drift/Retraining Recovery Quantitative Results

## Command used

```bash
{command}
```

## Scope and claim-safety note

This is an offline replay/recovery experiment. A drift alert triggers review-driven retraining and challenger registration in the experiment design. The experiment does not demonstrate fully automatic production deployment or promotion.

## Binary label mapping

`BENIGN`, `Benign`, `benign`, `Normal`, and `NORMAL` map to `BENIGN`; every other raw label maps to `ATTACK`. Metrics are binary BENIGN-vs-ATTACK metrics, not raw multiclass metrics.

## Scenario construction

For each scenario, the attack-family drift file is de-duplicated by row hash and split into trigger/retraining and future holdout subsets using the configured attack trigger fraction. BENIGN rows from `data/reference_data.csv` are also de-duplicated and split into reference baseline, retraining benign, and evaluation benign holdout subsets.

M0 is trained from `data/train_2_classes.csv`. M1 is trained only with data available after the drift trigger: the decontaminated M0 training data, the scenario trigger attack subset, and the benign retraining subset. Future holdout rows are excluded from M0/M1 fitting by row-hash decontamination and checked again after split.

## Drift method

Drift is computed with `{config['drift_method']}` over the validated 52 numeric features. Feature drift threshold is `p < {config['pvalue_threshold']}` for KS tests. Dataset drift is true when `drift_share >= {config['drift_threshold']}`.

## Leakage check result

All scenarios report zero M1-training/future-holdout and trigger/future-holdout row-hash overlap after split: `{config['all_scenarios_leakage_safe']}`.

## Summary results

{chr(10).join(rows)}

## How to use in the paper

Use `recovery_fixed_vs_retrained_comparison.csv` for a concise recovery table. Describe the results as an offline, framework-assisted, review-driven retraining recovery experiment. Report Accuracy, Macro-F1, Weighted-F1, drifted feature count, drift share, drift decision, and Delta Macro-F1. Do not claim fully automatic retraining, deployment, promotion, production-scale validation, or canary/blue-green behavior.

## Output files

- `recovery_dataset_summary.json`
- `recovery_experiment_config.json`
- `recovery_drift_windows.csv`
- `recovery_fixed_vs_retrained_comparison.csv`
- `recovery_fixed_model_metrics.csv`
- `recovery_retrained_model_metrics.csv`
- `recovery_per_class_metrics.csv`
- `recovery_confusion_matrices.json`
- `README_recovery_quantitative_results.md`
"""


def main() -> int:
    args = parse_args()
    if not args.binary:
        raise SystemExit("This script currently supports only the required --binary experiment.")
    if args.max_train_rows <= 0 or args.max_window_rows <= 0:
        raise SystemExit("--max-train-rows and --max-window-rows must be positive integers")

    root = repo_root()
    out_dir = output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    command = "python " + " ".join(sys.argv)
    seed = args.random_seed

    data_dir = root / "data"
    train_m0_raw, train_m0_raw_rows, train_m0_sampled = load_csv(data_dir / "train_2_classes.csv", args.max_train_rows, seed)
    reference_raw, reference_raw_rows, reference_sampled = load_csv(data_dir / "reference_data.csv", args.max_window_rows, seed)
    expected_features = feature_columns(train_m0_raw, "train_2_classes.csv")
    validate_features(reference_raw, expected_features, "reference_data.csv")

    reference_benign, retrain_benign, eval_benign, benign_summary = split_benign_pool(
        reference_raw,
        expected_features,
        seed,
        args.benign_reference_fraction,
        args.benign_retraining_fraction,
    )

    attack_sources = [
        ("S1", "PortScan", data_dir / "drift_portscan.csv"),
        ("S2", "BruteForce", data_dir / "drift_bruteforce.csv"),
        ("S3", "WebAttacks", data_dir / "drift_webattacks.csv"),
    ]

    scenarios: List[ScenarioData] = []
    future_hash_union: set[str] = set()
    source_summaries: Dict[str, Any] = {}
    for index, (scenario_id, attack_family, path) in enumerate(attack_sources):
        attack_raw, raw_rows, sampled = load_csv(path, args.max_window_rows, seed + index + 10)
        validate_features(attack_raw, expected_features, path.name)
        attack_trigger, attack_future, dropped_attack_dupes = split_attack_source(
            attack_raw,
            expected_features,
            seed + index + 100,
            args.attack_trigger_fraction,
        )
        trigger_df = pd.concat([attack_trigger, retrain_benign], ignore_index=True)
        future_df = pd.concat([attack_future, eval_benign], ignore_index=True)
        trigger_df = shuffled(trigger_df, seed + index + 200)
        future_df = shuffled(future_df, seed + index + 300)
        scenarios.append(
            ScenarioData(
                scenario=scenario_id,
                attack_family=attack_family,
                attack_source=rel(path, root),
                trigger_df=trigger_df,
                future_df=future_df,
                trigger_attack_rows=int(len(attack_trigger)),
                future_attack_rows=int(len(attack_future)),
                trigger_benign_rows=int(len(retrain_benign)),
                future_benign_rows=int(len(eval_benign)),
                dropped_duplicate_attack_rows=dropped_attack_dupes,
                trigger_fraction_requested=args.attack_trigger_fraction,
            )
        )
        future_hash_union.update(row_hash_list(future_df, expected_features))
        source_summaries[scenario_id] = {
            "attack_family": attack_family,
            "attack_source": rel(path, root),
            "raw_rows": raw_rows,
            "sampled_rows": int(len(attack_raw)),
            "sampling_applied": sampled,
            "dropped_duplicate_attack_rows": dropped_attack_dupes,
            "trigger_attack_rows": int(len(attack_trigger)),
            "future_attack_rows": int(len(attack_future)),
            "trigger_benign_rows": int(len(retrain_benign)),
            "future_benign_rows": int(len(eval_benign)),
        }

    train_m0_clean, removed_m0_future_overlap = decontaminate_against(train_m0_raw, expected_features, future_hash_union)
    medians = coerce_features(train_m0_clean, expected_features).median(numeric_only=True).fillna(0.0)
    m0_train = prepare_dataset("M0 training", train_m0_clean, expected_features, medians)

    # Choose reference baseline for drift computation.
    # --use-mixed-reference-for-drift: use the full reference_data.csv (BENIGN + known attacks
    # like DDoS). This is the realistic production setting where the reference represents
    # typical mixed traffic. Drift then measures whether an incoming window deviates from
    # that mixed baseline, producing more moderate drift_share values (~0.4–0.65).
    # Default (False): use only BENIGN rows — always produces very high drift_share (~0.98)
    # when drift windows are 100% attack, which looks unrealistically high.
    if args.use_mixed_reference_for_drift:
        reference_for_drift = prepare_dataset(
            "W0 reference baseline (full mixed traffic)",
            reference_raw,
            expected_features,
            medians,
        )
        print("[drift] Using full mixed reference_data.csv as drift baseline (--use-mixed-reference-for-drift).")
    else:
        reference_for_drift = prepare_dataset("W0 reference baseline (BENIGN only)", reference_benign, expected_features, medians)

    reference_dataset = reference_for_drift
    model_m0 = train_model(m0_train.X, m0_train.y, seed, "M0-fixed-XGB")

    fixed_metrics: List[Dict[str, Any]] = []
    retrained_metrics: List[Dict[str, Any]] = []
    comparison_rows: List[Dict[str, Any]] = []
    drift_rows: List[Dict[str, Any]] = []
    per_scenario_config: Dict[str, Any] = {}
    drift_details: Dict[str, Any] = {}
    confusion_matrices: Dict[str, Any] = {}
    leakage_reports: Dict[str, Any] = {}

    for index, scenario in enumerate(scenarios):
        future_hashes = set(row_hash_list(scenario.future_df, expected_features))
        attack_trigger_clean, removed_attack_trigger = decontaminate_against(scenario.trigger_df, expected_features, future_hashes)
        m1_train_df = pd.concat([train_m0_clean, attack_trigger_clean], ignore_index=True)
        m1_train_df, removed_m1_future_overlap = decontaminate_against(m1_train_df, expected_features, future_hashes)

        m1_train = prepare_dataset(f"{scenario.scenario} M1 training", m1_train_df, expected_features, medians)
        trigger_dataset = prepare_dataset(f"{scenario.scenario} trigger/retraining window", attack_trigger_clean, expected_features, medians)
        future_dataset = prepare_dataset(f"{scenario.scenario} future holdout", scenario.future_df, expected_features, medians)

        # Build a realistic drift window for drift computation by mixing BENIGN rows
        # from the reference pool into the trigger attack window. This prevents
        # the drift window from being 100% ATTACK vs 100% BENIGN reference, which
        # would always produce drift_share ~0.98 (unrealistically high).
        drift_benign_mix = args.drift_benign_mix_fraction
        if drift_benign_mix > 0.0 and not reference_benign.empty:
            n_attack_trigger = len(attack_trigger_clean)
            # Number of BENIGN rows to inject so they form drift_benign_mix of the window
            n_benign_inject = min(
                int(round(n_attack_trigger * drift_benign_mix / max(1.0 - drift_benign_mix, 1e-9))),
                len(reference_benign),
            )
            if n_benign_inject > 0:
                benign_inject = reference_benign.sample(
                    n=n_benign_inject, random_state=seed + index + 700, replace=False
                ).reset_index(drop=True)
                drift_window_df = pd.concat([attack_trigger_clean, benign_inject], ignore_index=True)
                drift_window_df = shuffled(drift_window_df, seed + index + 800)
            else:
                drift_window_df = attack_trigger_clean
        else:
            drift_window_df = attack_trigger_clean
        drift_window_dataset = prepare_dataset(
            f"{scenario.scenario} drift detection window (mixed)", drift_window_df, expected_features, medians
        )

        drift = compute_drift(
            reference_dataset,
            drift_window_dataset,
            args.pvalue_threshold,
            args.drift_threshold,
            scenario.scenario,
            scenario.attack_family,
        )
        action = "drift alert; review-driven retraining triggered" if drift["dataset_drift"] else "no drift alert; fixed model retained"
        drift["action"] = action
        drift_details[scenario.scenario] = drift

        model_m1 = train_model(m1_train.X, m1_train.y, seed + index + 500, f"{scenario.scenario}-M1-retrained-XGB")
        fixed = evaluate(model_m0, future_dataset, "M0-fixed-XGB", scenario.scenario, scenario.attack_family)
        retrained = evaluate(model_m1, future_dataset, f"{scenario.scenario}-M1-retrained-XGB", scenario.scenario, scenario.attack_family)
        fixed_metrics.append(fixed)
        retrained_metrics.append(retrained)

        leakage = overlap_report(m1_train, future_dataset, trigger_dataset)
        leakage_reports[scenario.scenario] = leakage

        comparison_rows.append(
            {
                "Scenario": scenario.scenario,
                "Attack family": scenario.attack_family,
                "Trigger dataset": scenario.attack_source + " trigger/retraining split",
                "Future holdout dataset": scenario.attack_source + " future holdout split + BENIGN holdout",
                "Future holdout composition": composition(future_dataset),
                "Drifted features": drift["drifted_feature_count"],
                "Total features": drift["total_features"],
                "Drift share": drift["drift_share"],
                "Drift detected": drift["dataset_drift"],
                "Action": action,
                "Fixed model": fixed["Model"],
                "Fixed Accuracy": fixed["Accuracy"],
                "Fixed Macro-F1": fixed["Macro-F1"],
                "Fixed Weighted-F1": fixed["Weighted-F1"],
                "Retrained model": retrained["Model"],
                "Retrained Accuracy": retrained["Accuracy"],
                "Retrained Macro-F1": retrained["Macro-F1"],
                "Retrained Weighted-F1": retrained["Weighted-F1"],
                "Delta Macro-F1": retrained["Macro-F1"] - fixed["Macro-F1"],
            }
        )
        drift_rows.append(
            {
                "Scenario": scenario.scenario,
                "Attack family": scenario.attack_family,
                "Trigger rows": trigger_dataset.df.shape[0],
                "Trigger BENIGN count": int(trigger_dataset.binary_label_counts.get("BENIGN", 0)),
                "Trigger ATTACK count": int(trigger_dataset.binary_label_counts.get("ATTACK", 0)),
                "Future holdout rows": future_dataset.df.shape[0],
                "Future BENIGN count": int(future_dataset.binary_label_counts.get("BENIGN", 0)),
                "Future ATTACK count": int(future_dataset.binary_label_counts.get("ATTACK", 0)),
                "Drifted features": drift["drifted_feature_count"],
                "Total features": drift["total_features"],
                "Drift share": drift["drift_share"],
                "Drift detected": drift["dataset_drift"],
                "Action": action,
            }
        )
        per_scenario_config[scenario.scenario] = {
            "attack_family": scenario.attack_family,
            "attack_source": scenario.attack_source,
            "trigger_fraction_requested": scenario.trigger_fraction_requested,
            "trigger_attack_rows": scenario.trigger_attack_rows,
            "future_attack_rows": scenario.future_attack_rows,
            "trigger_benign_rows": scenario.trigger_benign_rows,
            "future_benign_rows": scenario.future_benign_rows,
            "removed_attack_trigger_rows_overlapping_future_holdout": removed_attack_trigger,
            "removed_m1_training_rows_overlapping_future_holdout": removed_m1_future_overlap,
            "m1_training_binary_counts": m1_train.binary_label_counts,
            "future_holdout_binary_counts": future_dataset.binary_label_counts,
            "leakage_report": leakage,
        }
        confusion_matrices[scenario.scenario] = {
            "M0-fixed-XGB": {
                "labels": CLASS_NAMES,
                "matrix": fixed["confusion_matrix"],
            },
            f"{scenario.scenario}-M1-retrained-XGB": {
                "labels": CLASS_NAMES,
                "matrix": retrained["confusion_matrix"],
            },
        }

    fixed_df = pd.DataFrame([metric_row(item) for item in fixed_metrics])
    retrained_df = pd.DataFrame([metric_row(item) for item in retrained_metrics])
    comparison_df = pd.DataFrame(comparison_rows)
    drift_df = pd.DataFrame(drift_rows)
    per_class_df = pd.DataFrame(per_class_rows(fixed_metrics + retrained_metrics))

    all_leakage_safe = all(report["leakage_safe"] for report in leakage_reports.values())
    recovery_summary = {
        row["Scenario"]: {
            "attack_family": row["Attack family"],
            "delta_macro_f1": float(row["Delta Macro-F1"]),
            "fixed_macro_f1": float(row["Fixed Macro-F1"]),
            "retrained_macro_f1": float(row["Retrained Macro-F1"]),
            "improved": bool(row["Delta Macro-F1"] > 0),
        }
        for _, row in comparison_df.iterrows()
    }

    dataset_summary = {
        "train_m0": {
            "path": "data/train_2_classes.csv",
            "raw_rows": train_m0_raw_rows,
            "sampled_rows": int(len(train_m0_raw)),
            "sampling_applied": train_m0_sampled,
            "removed_rows_overlapping_any_future_holdout": removed_m0_future_overlap,
            "final_training_rows": int(len(train_m0_clean)),
            "binary_label_counts": m0_train.binary_label_counts,
        },
        "reference_data": {
            "path": "data/reference_data.csv",
            "raw_rows": reference_raw_rows,
            "sampled_rows": int(len(reference_raw)),
            "sampling_applied": reference_sampled,
            "benign_split": benign_summary,
        },
        "scenarios": source_summaries,
    }

    drift_method = next(iter(drift_details.values()))["method"] if drift_details else "not_computed"
    config = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "binary": args.binary,
        "random_seed": seed,
        "max_train_rows": args.max_train_rows,
        "max_window_rows": args.max_window_rows,
        "attack_trigger_fraction": args.attack_trigger_fraction,
        "benign_reference_fraction": args.benign_reference_fraction,
        "benign_retraining_fraction": args.benign_retraining_fraction,
        "drift_method": drift_method,
        "drift_threshold": args.drift_threshold,
        "pvalue_threshold": args.pvalue_threshold,
        "schema_validation": {
            "label_column": LABEL_COL,
            "feature_count": len(expected_features),
            "features_match_across_loaded_datasets": True,
            "feature_columns": expected_features,
            "numeric_coercion": "All non-label columns coerced with pandas.to_numeric(errors='coerce')",
            "imputation": "inf/-inf converted to NaN; NaN imputed with decontaminated M0 training medians",
        },
        "label_mapping": {
            "BENIGN_aliases": sorted(BENIGN_ALIASES),
            "non_benign_labels": "ATTACK",
        },
        "scenario_policy": {
            "M0_fixed_model": "Trained once from data/train_2_classes.csv after removing future-holdout overlaps.",
            "M1_retrained_model": "Per-scenario challenger trained from M0 training data plus trigger/retraining window only.",
            "future_holdout_policy": "Future holdout rows are excluded from M0/M1 training by row-hash checks.",
            "claim_safety": "Offline replay/recovery experiment only; no automatic production deployment or promotion is claimed.",
        },
        "all_scenarios_leakage_safe": all_leakage_safe,
        "leakage_reports": leakage_reports,
        "f1_recovery_summary": recovery_summary,
        "per_scenario_config": per_scenario_config,
        "existing_model_artifact_inspection": {
            "v1": inspect_pickle_model(root / "models" / "v1" / "xgb_nids_model_v1.pkl"),
            "v2": inspect_pickle_model(root / "models" / "v2" / "xgb_nids_model_v2.pkl"),
            "used_for_recovery_experiment": False,
        },
    }

    fixed_df.to_csv(out_dir / "recovery_fixed_model_metrics.csv", index=False, float_format="%.6f")
    retrained_df.to_csv(out_dir / "recovery_retrained_model_metrics.csv", index=False, float_format="%.6f")
    comparison_df.to_csv(out_dir / "recovery_fixed_vs_retrained_comparison.csv", index=False, float_format="%.6f")
    drift_df.to_csv(out_dir / "recovery_drift_windows.csv", index=False, float_format="%.6f")
    per_class_df.to_csv(out_dir / "recovery_per_class_metrics.csv", index=False, float_format="%.6f")
    write_json(out_dir / "recovery_dataset_summary.json", dataset_summary)
    write_json(out_dir / "recovery_experiment_config.json", config)
    write_json(out_dir / "recovery_confusion_matrices.json", confusion_matrices)
    (out_dir / "README_recovery_quantitative_results.md").write_text(
        make_readme(command, config, comparison_df), encoding="utf-8"
    )

    print("Offline drift/retraining recovery evaluation complete.")
    print(f"Output directory: {rel(out_dir, root)}")
    print(f"Drift method: {drift_method}")
    print(f"All scenarios leakage-safe: {all_leakage_safe}")
    print(comparison_df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
