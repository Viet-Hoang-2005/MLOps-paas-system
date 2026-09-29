#!/usr/bin/env python3
"""Offline NIDS drift/retraining quantitative evaluation.

Runs a binary BENIGN-vs-ATTACK offline replay experiment and writes paper-ready
CSV/JSON/README artifacts under paper/results/quantitative/. The script does not
mutate source datasets, source model artifacts, or the paper.
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

import numpy as np
import pandas as pd

try:
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
except ImportError as exc:  # pragma: no cover - dependency gate
    raise SystemExit(
        "Missing required dependency scikit-learn. Install it with: "
        "python -m pip install scikit-learn"
    ) from exc

try:
    from xgboost import XGBClassifier
except ImportError as exc:  # pragma: no cover - dependency gate
    raise SystemExit(
        "Missing required dependency xgboost. Install it with: python -m pip install xgboost"
    ) from exc

try:
    from scipy.stats import ks_2samp
except ImportError:  # pragma: no cover - fallback path
    ks_2samp = None

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

LABEL_COL = "Label"
CLASS_NAMES = ["BENIGN", "ATTACK"]
CLASS_TO_ID = {"BENIGN": 0, "ATTACK": 1}
BENIGN_ALIASES = {"BENIGN", "Benign", "benign", "Normal", "NORMAL", "normal"}


@dataclass
class DatasetSpec:
    key: str
    window: str
    path: Path
    role: str
    max_rows: int


@dataclass
class RawDataset:
    key: str
    window: str
    path: Path
    role: str
    raw_rows: int
    sampled_rows: int
    sampling_applied: bool
    removed_overlap_rows: int
    feature_columns: List[str]
    row_hash_list: List[str]
    df: pd.DataFrame

    @property
    def row_hashes(self) -> set[str]:
        return set(self.row_hash_list)


@dataclass
class PreparedDataset:
    key: str
    window: str
    path: Path
    role: str
    raw_rows: int
    sampled_rows: int
    sampling_applied: bool
    removed_overlap_rows: int
    raw_label_counts: Dict[str, int]
    binary_label_counts: Dict[str, int]
    feature_columns: List[str]
    row_hash_list: List[str]
    X: pd.DataFrame
    y: np.ndarray
    y_labels: List[str]

    @property
    def row_hashes(self) -> set[str]:
        return set(self.row_hash_list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an offline binary NIDS drift/retraining replay experiment."
    )
    parser.add_argument(
        "--binary",
        action="store_true",
        help="Run the required BENIGN-vs-ATTACK binary projection experiment.",
    )
    parser.add_argument("--drift-threshold", type=float, default=0.5)
    parser.add_argument("--pvalue-threshold", type=float, default=0.05)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--max-train-rows", type=int, default=100000)
    parser.add_argument("--max-window-rows", type=int, default=50000)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def output_dir() -> Path:
    return Path(__file__).resolve().parent


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


def sample_df(df: pd.DataFrame, max_rows: int, seed: int) -> Tuple[pd.DataFrame, bool]:
    if max_rows <= 0 or len(df) <= max_rows:
        return df.copy().reset_index(drop=True), False
    sampled = df.sample(n=max_rows, random_state=seed).sort_index().reset_index(drop=True)
    return sampled, True


def detect_feature_columns(df: pd.DataFrame, dataset_name: str) -> List[str]:
    if LABEL_COL not in df.columns:
        raise ValueError(f"{dataset_name} does not contain required label column '{LABEL_COL}'")
    return [column for column in df.columns if column != LABEL_COL]


def coerce_features(df: pd.DataFrame, feature_columns: Sequence[str]) -> pd.DataFrame:
    X = df.loc[:, list(feature_columns)].apply(pd.to_numeric, errors="coerce")
    return X.replace([np.inf, -np.inf], np.nan)


def compute_training_medians(X: pd.DataFrame) -> pd.Series:
    return X.median(numeric_only=True).fillna(0.0)


def apply_medians(X: pd.DataFrame, medians: pd.Series) -> pd.DataFrame:
    return X.fillna(medians).fillna(0.0)


def row_hash_list(df: pd.DataFrame, feature_columns: Sequence[str]) -> List[str]:
    """Return ordered row hashes over numeric features plus binary label.

    The binary label is used intentionally because the experiment evaluates a
    binary projection; this catches same-row leakage even if attack subclasses
    differ in raw label spelling across files.
    """

    normalized = coerce_features(df, feature_columns)
    normalized["__binary_label__"] = [normalize_label(value) for value in df[LABEL_COL].tolist()]
    hashed = pd.util.hash_pandas_object(normalized, index=False).astype("uint64")
    return [hashlib.sha256(str(int(value)).encode("utf-8")).hexdigest() for value in hashed.to_numpy()]


def load_raw_dataset(spec: DatasetSpec, expected_features: Optional[List[str]], seed: int) -> RawDataset:
    if not spec.path.exists():
        raise FileNotFoundError(f"Missing dataset: {spec.path}")
    df = pd.read_csv(spec.path)
    raw_rows = int(len(df))
    df, sampled = sample_df(df, spec.max_rows, seed)
    feature_columns = detect_feature_columns(df, spec.key)
    if expected_features is not None and feature_columns != expected_features:
        missing = sorted(set(expected_features) - set(feature_columns))
        extra = sorted(set(feature_columns) - set(expected_features))
        raise ValueError(
            f"Feature schema mismatch for {spec.key}: missing={missing[:10]}, extra={extra[:10]}"
        )
    hashes = row_hash_list(df, feature_columns)
    return RawDataset(
        key=spec.key,
        window=spec.window,
        path=spec.path,
        role=spec.role,
        raw_rows=raw_rows,
        sampled_rows=int(len(df)),
        sampling_applied=sampled,
        removed_overlap_rows=0,
        feature_columns=feature_columns,
        row_hash_list=hashes,
        df=df,
    )


def decontaminate_training_raw(train: RawDataset, eval_hashes: set[str]) -> RawDataset:
    keep_mask = np.array([row_hash not in eval_hashes for row_hash in train.row_hash_list], dtype=bool)
    removed = int((~keep_mask).sum())
    if removed == 0:
        return train
    clean_df = train.df.loc[keep_mask].reset_index(drop=True)
    clean_hashes = [row_hash for row_hash, keep in zip(train.row_hash_list, keep_mask) if keep]
    return RawDataset(
        key=train.key,
        window=train.window,
        path=train.path,
        role=train.role + " (decontaminated against evaluation windows)",
        raw_rows=train.raw_rows,
        sampled_rows=int(len(clean_df)),
        sampling_applied=train.sampling_applied,
        removed_overlap_rows=removed,
        feature_columns=train.feature_columns,
        row_hash_list=clean_hashes,
        df=clean_df,
    )


def prepare_dataset(raw: RawDataset, medians: pd.Series) -> PreparedDataset:
    X = apply_medians(coerce_features(raw.df, raw.feature_columns), medians)
    y_labels = [normalize_label(value) for value in raw.df[LABEL_COL].tolist()]
    y = np.array([CLASS_TO_ID[label] for label in y_labels], dtype=np.int64)
    raw_counts = raw.df[LABEL_COL].astype(str).value_counts(dropna=False).to_dict()
    binary_counts = pd.Series(y_labels).value_counts().reindex(CLASS_NAMES, fill_value=0).to_dict()
    return PreparedDataset(
        key=raw.key,
        window=raw.window,
        path=raw.path,
        role=raw.role,
        raw_rows=raw.raw_rows,
        sampled_rows=raw.sampled_rows,
        sampling_applied=raw.sampling_applied,
        removed_overlap_rows=raw.removed_overlap_rows,
        raw_label_counts={str(k): int(v) for k, v in raw_counts.items()},
        binary_label_counts={str(k): int(v) for k, v in binary_counts.items()},
        feature_columns=raw.feature_columns,
        row_hash_list=raw.row_hash_list,
        X=X,
        y=y,
        y_labels=y_labels,
    )


def train_model(X: pd.DataFrame, y: np.ndarray, seed: int, name: str) -> XGBClassifier:
    counts = np.bincount(y, minlength=2)
    if counts[0] == 0 or counts[1] == 0:
        raise ValueError(f"{name} training data must contain both BENIGN and ATTACK after binary mapping")
    scale_pos_weight = float(counts[0] / counts[1]) if counts[1] else 1.0
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
        scale_pos_weight=scale_pos_weight,
    )
    model.fit(X, y)
    return model


def evaluate_model(model: XGBClassifier, dataset: PreparedDataset, model_name: str) -> Dict[str, Any]:
    y_pred = np.asarray(model.predict(dataset.X), dtype=np.int64)
    report = classification_report(
        dataset.y,
        y_pred,
        labels=[0, 1],
        target_names=CLASS_NAMES,
        output_dict=True,
        zero_division=0,
    )
    return {
        "Window": dataset.window,
        "Dataset": dataset.path.name,
        "Model": model_name,
        "Accuracy": float(accuracy_score(dataset.y, y_pred)),
        "Macro-F1": float(f1_score(dataset.y, y_pred, average="macro", zero_division=0)),
        "Weighted-F1": float(f1_score(dataset.y, y_pred, average="weighted", zero_division=0)),
        "per_class": {
            label: {
                "precision": float(report[label]["precision"]),
                "recall": float(report[label]["recall"]),
                "f1-score": float(report[label]["f1-score"]),
                "support": int(report[label]["support"]),
            }
            for label in CLASS_NAMES
        },
        "confusion_matrix": confusion_matrix(dataset.y, y_pred, labels=[0, 1]).tolist(),
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


def compute_drift(
    reference: PreparedDataset,
    current: PreparedDataset,
    pvalue_threshold: float,
    drift_threshold: float,
) -> Dict[str, Any]:
    drifted_features: List[str] = []
    feature_results: Dict[str, Dict[str, Any]] = {}
    method = "ks_2samp" if ks_2samp is not None else "psi_fallback"

    for feature in reference.feature_columns:
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
            feature_results[feature] = {
                "method": method,
                "psi": score,
                "threshold": 0.2,
                "drifted": drifted,
            }
        if drifted:
            drifted_features.append(feature)

    total_features = len(reference.feature_columns)
    drift_share = len(drifted_features) / total_features if total_features else 0.0
    return {
        "Window": current.window,
        "Dataset": current.path.name,
        "method": method,
        "total_features": int(total_features),
        "drifted_feature_count": int(len(drifted_features)),
        "drift_share": float(drift_share),
        "dataset_drift": bool(drift_share >= drift_threshold),
        "drift_threshold": drift_threshold,
        "drifted_features": drifted_features,
        "feature_results": feature_results,
    }


def inspect_label_json(path: Path) -> Optional[List[str]]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(data, list):
        return [str(item) for item in data]
    if isinstance(data, dict):
        for key in ("classes", "label_classes", "labels"):
            if isinstance(data.get(key), list):
                return [str(item) for item in data[key]]
        return [str(k) for k in data.keys()]
    return None


def inspect_pickle_model(path: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "loaded": False,
        "load_error": None,
        "type": None,
        "n_features_in_": None,
        "classes_": None,
    }
    if not path.exists():
        return info
    try:
        with path.open("rb") as handle:
            model = pickle.load(handle)
        info["loaded"] = True
        info["type"] = f"{type(model).__module__}.{type(model).__name__}"
        if hasattr(model, "n_features_in_"):
            info["n_features_in_"] = int(getattr(model, "n_features_in_"))
        elif hasattr(model, "get_booster"):
            try:
                info["n_features_in_"] = int(model.get_booster().num_features())
            except Exception:
                pass
        if hasattr(model, "classes_"):
            info["classes_"] = [str(item) for item in list(getattr(model, "classes_"))]
    except Exception as exc:
        info["load_error"] = repr(exc)
    return info


def inspect_existing_models(root: Path, expected_feature_count: int) -> Dict[str, Any]:
    candidates = {
        "v1": {
            "model_path": root / "models" / "v1" / "xgb_nids_model_v1.pkl",
            "label_path": root / "models" / "v1" / "label_classes_v1.json",
            "metrics_path": root / "models" / "v1" / "metrics_v1.json",
        },
        "v2": {
            "model_path": root / "models" / "v2" / "xgb_nids_model_v2.pkl",
            "label_path": root / "models" / "v2" / "label_classes_v2.json",
            "metrics_path": root / "models" / "v2" / "metrics_v2.json",
        },
        "mlflow_package_v2": {
            "model_path": root / "models" / "nids-model-mlflow-package" / "model" / "model.ubj",
            "label_path": root / "models" / "nids-model-mlflow-package" / "model" / "label_classes_v2.json",
            "metrics_path": root / "models" / "nids-model-mlflow-package" / "model" / "MLmodel",
        },
    }
    result: Dict[str, Any] = {
        "note": "Existing artifacts are inspected for compatibility only; this experiment trains fresh M0/M1 models by default.",
        "expected_feature_count": int(expected_feature_count),
        "artifacts": {},
    }
    for name, paths in candidates.items():
        model_path = paths["model_path"]
        label_classes = inspect_label_json(paths["label_path"])
        if model_path.suffix == ".pkl":
            model_info = inspect_pickle_model(model_path)
        else:
            model_info = {
                "path": str(model_path),
                "exists": model_path.exists(),
                "loaded": False,
                "load_error": "Not a pickle artifact; not loaded by this offline evaluator.",
                "type": None,
                "n_features_in_": None,
                "classes_": None,
            }
        n_features = model_info.get("n_features_in_")
        feature_compatible = n_features in (None, expected_feature_count)
        normalized = [normalize_label(label) for label in label_classes] if label_classes else []
        binary_projection_possible = bool(label_classes) and set(normalized).issubset({"BENIGN", "ATTACK"})
        result["artifacts"][name] = {
            "model": model_info,
            "label_classes_path": str(paths["label_path"]),
            "label_classes": label_classes,
            "normalized_binary_labels": normalized,
            "metrics_path": str(paths["metrics_path"]),
            "metrics_exists": paths["metrics_path"].exists(),
            "feature_compatible": bool(feature_compatible),
            "binary_projection_possible": bool(binary_projection_possible),
            "used_for_experiment": False,
        }
    return result


def dataset_summary(datasets: Dict[str, PreparedDataset], root: Path) -> Dict[str, Any]:
    return {
        key: {
            "path": rel(ds.path, root),
            "role": ds.role,
            "window": ds.window,
            "raw_rows": ds.raw_rows,
            "sampled_rows": ds.sampled_rows,
            "sampling_applied": ds.sampling_applied,
            "removed_overlap_rows": ds.removed_overlap_rows,
            "columns": len(ds.feature_columns) + 1,
            "feature_count": len(ds.feature_columns),
            "label_column": LABEL_COL,
            "raw_label_counts": ds.raw_label_counts,
            "binary_label_counts": ds.binary_label_counts,
        }
        for key, ds in datasets.items()
    }


def leakage_checks(training_sets: Dict[str, PreparedDataset], eval_sets: Dict[str, PreparedDataset]) -> Dict[str, Any]:
    checks: Dict[str, Any] = {}
    any_overlap = False
    for train_name, train_ds in training_sets.items():
        for eval_name, eval_ds in eval_sets.items():
            eval_hashes = eval_ds.row_hashes
            train_hashes = train_ds.row_hashes
            unique_overlap = train_hashes.intersection(eval_hashes)
            overlapping_train_rows = sum(1 for row_hash in train_ds.row_hash_list if row_hash in eval_hashes)
            overlapping_eval_rows = sum(1 for row_hash in eval_ds.row_hash_list if row_hash in train_hashes)
            any_overlap = any_overlap or bool(unique_overlap)
            checks[f"{train_name}_vs_{eval_name}"] = {
                "train_dataset": train_ds.path.name,
                "eval_dataset": eval_ds.path.name,
                "unique_overlap_count": int(len(unique_overlap)),
                "overlapping_training_rows": int(overlapping_train_rows),
                "overlapping_eval_rows": int(overlapping_eval_rows),
                "train_rows": train_ds.sampled_rows,
                "eval_rows": eval_ds.sampled_rows,
                "overlap_ratio_eval": float(overlapping_eval_rows / eval_ds.sampled_rows) if eval_ds.sampled_rows else 0.0,
            }
    return {
        "method": "SHA-256 over pandas row hash of numeric feature columns plus normalized binary Label",
        "training_rows_removed_before_fit": True,
        "any_overlap_detected_after_decontamination": bool(any_overlap),
        "checks": checks,
    }


def metric_row(metrics: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "Window": metrics["Window"],
        "Dataset": metrics["Dataset"],
        "Model": metrics["Model"],
        "Accuracy": metrics["Accuracy"],
        "Macro-F1": metrics["Macro-F1"],
        "Weighted-F1": metrics["Weighted-F1"],
    }


def per_class_rows(metrics_list: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for metrics in metrics_list:
        for class_name, values in metrics["per_class"].items():
            rows.append(
                {
                    "Window": metrics["Window"],
                    "Dataset": metrics["Dataset"],
                    "Model": metrics["Model"],
                    "Class": class_name,
                    "Precision": values["precision"],
                    "Recall": values["recall"],
                    "F1": values["f1-score"],
                    "Support": values["support"],
                }
            )
    return rows


def data_composition(dataset: PreparedDataset) -> str:
    benign = int(dataset.binary_label_counts.get("BENIGN", 0))
    attack = int(dataset.binary_label_counts.get("ATTACK", 0))
    return f"BENIGN={benign}, ATTACK={attack}"


def make_readme(
    command: str,
    args: argparse.Namespace,
    summaries: Dict[str, Any],
    drift_method: str,
    leakage: Dict[str, Any],
    comparison_df: pd.DataFrame,
) -> str:
    files_used = "\n".join(f"- `{info['path']}` ({info['role']})" for info in summaries.values())
    leakage_line = (
        "No row-hash overlap was detected after removing overlapping training rows before model fitting."
        if not leakage["any_overlap_detected_after_decontamination"]
        else "Row-hash overlap remains after decontamination; inspect experiment_config.json before citing these numbers."
    )
    result_lines = []
    for _, row in comparison_df.iterrows():
        result_lines.append(
            f"- {row['Window']} `{row['Dataset']}`: drift_share={row['Drift share']:.3f}, "
            f"fixed Macro-F1={row['Fixed Macro-F1']:.4f}, "
            f"framework Macro-F1={row['Framework Macro-F1']:.4f}, "
            f"Delta Macro-F1={row['Delta Macro-F1']:.4f}."
        )
    return f"""# Offline Drift/Retraining Quantitative Results

## Command used

```bash
{command}
```

## Data files used

{files_used}

## Binary label mapping

The experiment maps `BENIGN`, `Benign`, `benign`, `Normal`, and `NORMAL` to `BENIGN`. Every other label is mapped to `ATTACK`. Raw multiclass labels are not compared directly.

## Model training sources

- Fixed baseline model `M0-fixed-XGB`: trained freshly and reproducibly on `data/train_2_classes.csv` after removing rows that overlap evaluation windows by row hash.
- Challenger/retrained model `M1-challenger-XGB`: trained freshly and reproducibly on `data/train_5_classes.csv` after removing rows that overlap evaluation windows by row hash.
- Existing `models/v1` and `models/v2` artifacts are inspected for compatibility only and are not used for metric generation.

## Drift method

Drift is computed between `data/reference_data.csv` and each replay window over the validated 52-feature schema. Method used: `{drift_method}`. Dataset drift is true when `drift_share >= {args.drift_threshold}`. For KS drift, feature drift is true when `p < {args.pvalue_threshold}`. If SciPy is unavailable, the script falls back to a documented PSI-style threshold.

## Threshold

- Feature-level p-value threshold: `{args.pvalue_threshold}`.
- Dataset-level drift-share threshold: `{args.drift_threshold}`.

## Leakage check result

{leakage_line}

The leakage check uses row hashes over numeric feature columns plus normalized binary `Label`. See `experiment_config.json` for per-pair overlap counts and removed training-row counts.

## Summary results

{chr(10).join(result_lines)}

## How to cite/use these numbers in the paper

Use `fixed_vs_framework_comparison.csv` for the main quantitative table. Phrase the experiment as an offline replay comparing a fixed baseline model with a framework-assisted path where a drift alert triggers review-driven retraining/registration. In the active-model comparison, the first detected drift window is the alert/review trigger and the challenger is used for subsequent windows. Report Accuracy, Macro-F1, Weighted-F1, drifted feature count, drift share, drift decision, and Delta Macro-F1. Avoid describing the path as fully automatic production deployment or automatic promotion.

## Claim-safety note

This is an offline replay experiment. It does not demonstrate production-scale validation or fully automatic deployment/promotion.

## Output files

- `dataset_summary.json`
- `model_compatibility.json`
- `drift_windows.csv`
- `drift_results.json`
- `fixed_model_metrics.csv`
- `challenger_model_metrics.csv`
- `fixed_vs_framework_comparison.csv`
- `per_class_metrics.csv`
- `confusion_matrices.json`
- `experiment_config.json`
- `README_quantitative_results.md`
"""


def main() -> int:
    args = parse_args()
    if not args.binary:
        raise SystemExit("This script currently supports only the required --binary experiment.")
    if args.max_train_rows <= 0 or args.max_window_rows <= 0:
        raise SystemExit("--max-train-rows and --max-window-rows must be positive integers")

    root = repo_root()
    out_dir = output_dir()
    seed = args.random_seed
    command = "python " + " ".join(sys.argv)

    specs = [
        DatasetSpec("train_m0", "TRAIN-M0", root / "data" / "train_2_classes.csv", "fixed baseline training", args.max_train_rows),
        DatasetSpec("train_m1", "TRAIN-M1", root / "data" / "train_5_classes.csv", "challenger training", args.max_train_rows),
        DatasetSpec("reference", "W0", root / "data" / "reference_data.csv", "reference drift baseline", args.max_window_rows),
        DatasetSpec("w1", "W1", root / "data" / "test_data.csv", "similar/holdout replay window", args.max_window_rows),
        DatasetSpec("w2", "W2", root / "data" / "drift_portscan.csv", "drift replay window", args.max_window_rows),
        DatasetSpec("w3", "W3", root / "data" / "drift_bruteforce.csv", "drift replay window", args.max_window_rows),
        DatasetSpec("w4", "W4", root / "data" / "drift_webattacks.csv", "drift replay window", args.max_window_rows),
        DatasetSpec("w5", "W5", root / "data" / "portscan.csv", "optional drift replay window", args.max_window_rows),
    ]

    first_raw = pd.read_csv(specs[0].path)
    expected_features = detect_feature_columns(first_raw, specs[0].key)

    raw_datasets: Dict[str, RawDataset] = {}
    for spec in specs:
        if spec.key == "w5" and not spec.path.exists():
            continue
        raw_datasets[spec.key] = load_raw_dataset(spec, expected_features, seed)

    eval_keys = [key for key in ["w1", "w2", "w3", "w4", "w5"] if key in raw_datasets]
    eval_hashes: set[str] = set()
    for key in eval_keys:
        eval_hashes.update(raw_datasets[key].row_hashes)

    raw_datasets["train_m0"] = decontaminate_training_raw(raw_datasets["train_m0"], eval_hashes)
    raw_datasets["train_m1"] = decontaminate_training_raw(raw_datasets["train_m1"], eval_hashes)

    median_source_X = coerce_features(raw_datasets["train_m0"].df, expected_features)
    medians = compute_training_medians(median_source_X)
    datasets = {key: prepare_dataset(raw, medians) for key, raw in raw_datasets.items()}

    schema_validation = {
        "label_column": LABEL_COL,
        "feature_count": len(expected_features),
        "features_match_across_loaded_datasets": True,
        "feature_columns": expected_features,
        "numeric_coercion": "All non-label columns coerced with pandas.to_numeric(errors='coerce')",
        "imputation": "inf/-inf converted to NaN; NaN imputed with decontaminated M0 training medians",
    }

    model_compatibility = inspect_existing_models(root, len(expected_features))

    model_m0 = train_model(datasets["train_m0"].X, datasets["train_m0"].y, seed, "M0-fixed-XGB")
    model_m1 = train_model(datasets["train_m1"].X, datasets["train_m1"].y, seed, "M1-challenger-XGB")

    drift_results: Dict[str, Any] = {}
    first_drift_seen = False
    for key in eval_keys:
        drift = compute_drift(datasets["reference"], datasets[key], args.pvalue_threshold, args.drift_threshold)
        if drift["dataset_drift"]:
            if not first_drift_seen:
                action = "alert/review-driven retraining triggered"
                first_drift_seen = True
            else:
                action = "drift alert observed; review-driven retrained model already active"
        else:
            action = "no drift alert; continue fixed baseline monitoring"
        drift["action"] = action
        drift_results[key] = drift

    fixed_metrics = {key: evaluate_model(model_m0, datasets[key], "M0-fixed-XGB") for key in eval_keys}
    challenger_metrics = {key: evaluate_model(model_m1, datasets[key], "M1-challenger-XGB") for key in eval_keys}

    framework_active_metrics: Dict[str, Dict[str, Any]] = {}
    retrained_model_active = False
    for key in eval_keys:
        framework_active_metrics[key] = challenger_metrics[key] if retrained_model_active else fixed_metrics[key]
        if drift_results[key]["dataset_drift"] and not retrained_model_active:
            retrained_model_active = True

    fixed_df = pd.DataFrame([metric_row(fixed_metrics[key]) for key in eval_keys])
    challenger_df = pd.DataFrame([metric_row(challenger_metrics[key]) for key in eval_keys])

    comparison_rows: List[Dict[str, Any]] = []
    drift_window_rows: List[Dict[str, Any]] = []
    for key in eval_keys:
        ds = datasets[key]
        drift = drift_results[key]
        fixed = fixed_metrics[key]
        framework = framework_active_metrics[key]
        comparison_rows.append(
            {
                "Window": ds.window,
                "Dataset": ds.path.name,
                "Data composition": data_composition(ds),
                "Drifted features": drift["drifted_feature_count"],
                "Total features": drift["total_features"],
                "Drift share": drift["drift_share"],
                "Drift detected": drift["dataset_drift"],
                "Action": drift["action"],
                "Fixed model": fixed["Model"],
                "Fixed Accuracy": fixed["Accuracy"],
                "Fixed Macro-F1": fixed["Macro-F1"],
                "Fixed Weighted-F1": fixed["Weighted-F1"],
                "Framework active model": framework["Model"],
                "Framework Accuracy": framework["Accuracy"],
                "Framework Macro-F1": framework["Macro-F1"],
                "Framework Weighted-F1": framework["Weighted-F1"],
                "Delta Macro-F1": framework["Macro-F1"] - fixed["Macro-F1"],
            }
        )
        benign = int(ds.binary_label_counts.get("BENIGN", 0))
        attack = int(ds.binary_label_counts.get("ATTACK", 0))
        drift_window_rows.append(
            {
                "Window": ds.window,
                "Dataset": ds.path.name,
                "Rows": ds.sampled_rows,
                "BENIGN count": benign,
                "ATTACK count": attack,
                "Attack ratio": float(attack / ds.sampled_rows) if ds.sampled_rows else 0.0,
                "Drifted features": drift["drifted_feature_count"],
                "Drift share": drift["drift_share"],
                "Drift detected": drift["dataset_drift"],
                "Action": drift["action"],
            }
        )

    comparison_df = pd.DataFrame(comparison_rows)
    drift_windows_df = pd.DataFrame(drift_window_rows)
    all_metrics = list(fixed_metrics.values()) + list(challenger_metrics.values())
    per_class_df = pd.DataFrame(per_class_rows(all_metrics))
    confusion_matrices = {
        "M0-fixed-XGB": {
            key: {
                "Window": fixed_metrics[key]["Window"],
                "Dataset": fixed_metrics[key]["Dataset"],
                "labels": CLASS_NAMES,
                "matrix": fixed_metrics[key]["confusion_matrix"],
            }
            for key in eval_keys
        },
        "M1-challenger-XGB": {
            key: {
                "Window": challenger_metrics[key]["Window"],
                "Dataset": challenger_metrics[key]["Dataset"],
                "labels": CLASS_NAMES,
                "matrix": challenger_metrics[key]["confusion_matrix"],
            }
            for key in eval_keys
        },
    }

    eval_sets = {key: datasets[key] for key in eval_keys}
    leakage = leakage_checks(
        {"train_m0": datasets["train_m0"], "train_m1": datasets["train_m1"]}, eval_sets
    )
    summaries = dataset_summary(datasets, root)
    drift_method = next(iter(drift_results.values()))["method"] if drift_results else "not_computed"
    activated = comparison_df[comparison_df["Framework active model"] == "M1-challenger-XGB"]
    f1_recovery_summary = {
        "delta_macro_f1_by_window": {
            str(row["Window"]): float(row["Delta Macro-F1"]) for _, row in comparison_df.iterrows()
        },
        "mean_delta_macro_f1_after_retrained_model_active": float(activated["Delta Macro-F1"].mean()) if not activated.empty else 0.0,
        "first_drift_window_is_trigger_not_instant_promotion": True,
    }

    config = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "binary": args.binary,
        "random_seed": seed,
        "max_train_rows": args.max_train_rows,
        "max_window_rows": args.max_window_rows,
        "drift_threshold": args.drift_threshold,
        "pvalue_threshold": args.pvalue_threshold,
        "schema_validation": schema_validation,
        "label_mapping": {
            "BENIGN_aliases": sorted(BENIGN_ALIASES),
            "non_benign_labels": "ATTACK",
        },
        "training_sources": {
            "M0-fixed-XGB": "data/train_2_classes.csv",
            "M1-challenger-XGB": "data/train_5_classes.csv",
            "decontamination": "Rows overlapping any evaluation window by row hash are removed before fitting.",
        },
        "framework_path_policy": {
            "before_drift_trigger": "M0-fixed-XGB",
            "first_detected_drift_window": "alert/review trigger; not counted as instant production promotion",
            "subsequent_windows_after_first_detected_drift": "M1-challenger-XGB active in offline replay comparison",
            "claim_safety": "Offline replay only; no automatic production deployment or promotion is claimed.",
        },
        "f1_recovery_summary": f1_recovery_summary,
        "leakage_checks": leakage,
    }

    fixed_df.to_csv(out_dir / "fixed_model_metrics.csv", index=False, float_format="%.6f")
    challenger_df.to_csv(out_dir / "challenger_model_metrics.csv", index=False, float_format="%.6f")
    comparison_df.to_csv(out_dir / "fixed_vs_framework_comparison.csv", index=False, float_format="%.6f")
    drift_windows_df.to_csv(out_dir / "drift_windows.csv", index=False, float_format="%.6f")
    per_class_df.to_csv(out_dir / "per_class_metrics.csv", index=False, float_format="%.6f")

    write_json(out_dir / "dataset_summary.json", summaries)
    write_json(out_dir / "model_compatibility.json", model_compatibility)
    write_json(out_dir / "drift_results.json", drift_results)
    write_json(out_dir / "confusion_matrices.json", confusion_matrices)
    write_json(out_dir / "experiment_config.json", config)
    (out_dir / "README_quantitative_results.md").write_text(
        make_readme(command, args, summaries, drift_method, leakage, comparison_df), encoding="utf-8"
    )

    print("Offline drift/retraining evaluation complete.")
    print(f"Output directory: {rel(out_dir, root)}")
    print(f"Evaluation windows: {', '.join(eval_keys)}")
    print(f"Drift method: {drift_method}")
    print(
        "Training rows removed before fit: "
        f"M0={datasets['train_m0'].removed_overlap_rows}, "
        f"M1={datasets['train_m1'].removed_overlap_rows}"
    )
    print(
        "Any row-hash overlap detected after decontamination: "
        f"{leakage['any_overlap_detected_after_decontamination']}"
    )
    print(comparison_df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
