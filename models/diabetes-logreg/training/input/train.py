"""Diabetes 30-day Readmission Logistic Regression trainer for MLOps-PaaS workspaces."""

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

DEFAULTS = {
    "train_csv": "data/training_data.csv",
    "feature_schema": "feature_schema.json",
    "label_column": "Label",
    "seed": 445,
    "validation_fraction": 0.2,
    "C": 1.0,
    "solver": "lbfgs",
    "class_weight": "balanced",
    "max_iter": 2000,
    "threshold": 0.5,
}

CLASSES = [
    "No Readmission within 30 Days",
    "Readmission within 30 Days",
]

LABEL_ALIASES = {
    "0": 0,
    "no readmission within 30 days": 0,
    "no": 0,
    "1": 1,
    "readmission within 30 days": 1,
    "<30": 1,
}

ALLOWED_SOLVERS = {"lbfgs", "liblinear", "newton-cg", "newton-cholesky", "sag", "saga"}


class TrainingError(RuntimeError):
    """A safe, actionable failure for the training terminal."""


def log(message: str) -> None:
    print(message, flush=True)


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def file_sha256(stream) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def input_file(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Input paths must be non-empty strings.")
    path = (root / value).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"Input must be an existing file inside Input: {value}")
    return path


def load_config(root: Path, config_path: str) -> dict:
    supplied = json.loads(input_file(root, config_path).read_text(encoding="utf-8"))
    if not isinstance(supplied, dict) or set(supplied) - set(DEFAULTS):
        raise ValueError(
            "config.json must be an object containing only documented options."
        )
    config = {**DEFAULTS, **supplied}
    if (
        not isinstance(config["label_column"], str)
        or not config["label_column"].strip()
    ):
        raise ValueError("label_column is required.")
    config["label_column"] = config["label_column"].strip()

    for key in ("seed", "max_iter"):
        value = config[key]
        if type(value) is not int or value < (0 if key == "seed" else 1):
            raise ValueError(f"{key} must be a positive integer (seed may be zero).")
    if config["seed"] > np.iinfo(np.uint32).max:
        raise ValueError("seed must fit an unsigned 32-bit integer.")

    for key in ("validation_fraction", "threshold"):
        value = config[key]
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not 0 < value < 1
        ):
            raise ValueError(f"{key} must be a finite number strictly between 0 and 1.")

    c_val = config["C"]
    if type(c_val) not in (int, float) or not math.isfinite(c_val) or c_val <= 0:
        raise ValueError("C must be a finite positive number.")

    if not isinstance(config["solver"], str) or config["solver"] not in ALLOWED_SOLVERS:
        raise ValueError(f"solver must be one of {sorted(ALLOWED_SOLVERS)}.")

    if config["class_weight"] not in ("balanced", None, "none"):
        raise ValueError("class_weight must be 'balanced', 'none', or null.")

    return config


def load_schema(root: Path, filename: str) -> tuple[list[str], list[str], list[str]]:
    payload = json.loads(input_file(root, filename).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("feature_schema.json must be a JSON object.")
    numeric = payload.get("numeric_features")
    categorical = payload.get("categorical_features")
    if (
        not isinstance(numeric, list)
        or not isinstance(categorical, list)
        or not numeric
        or not categorical
    ):
        raise ValueError(
            "feature_schema.json must define non-empty numeric_features and categorical_features lists."
        )
    for group in (numeric, categorical):
        if any(not isinstance(col, str) or not col.strip() or col != col.strip() for col in group):
            raise ValueError("All feature names in feature_schema.json must be trimmed non-empty strings.")
    all_features = payload.get("feature_order") or (numeric + categorical)
    if (
        not isinstance(all_features, list)
        or len(all_features) != len(numeric) + len(categorical)
        or set(all_features) != set(numeric) | set(categorical)
    ):
        raise ValueError(
            "feature_schema.json feature_order must contain the exact union of numeric_features and categorical_features."
        )
    if len(set(all_features)) != len(all_features):
        raise ValueError("feature_schema.json contains duplicate feature names.")
    return numeric, categorical, all_features


def map_target_series(raw_labels: pd.Series) -> pd.Series:
    normalized = raw_labels.astype("string").str.strip().str.lower()
    mapped = normalized.map(LABEL_ALIASES)
    return mapped


def load_data(
    path: Path,
    numeric_cols: list[str],
    categorical_cols: list[str],
    all_features: list[str],
    config: dict,
) -> tuple[pd.DataFrame, np.ndarray, dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        header = next(csv.reader(stream), [])
    columns = [c.strip() for c in header]
    label_col = config["label_column"]
    if len(set(columns)) != len(columns):
        raise ValueError("Duplicate CSV columns after trimming whitespace.")
    expected = set(all_features) | {label_col}
    if label_col in all_features or set(columns) != expected:
        raise ValueError(
            f"CSV schema mismatch: missing={sorted(expected - set(columns))}, extra={sorted(set(columns) - expected)}"
        )

    frame = pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False, low_memory=False)
    frame.columns = columns

    mapped_labels = map_target_series(frame[label_col])
    has_valid_label = mapped_labels.notna()

    numeric_df = frame[numeric_cols].apply(pd.to_numeric, errors="coerce").astype("float64")
    finite = np.isfinite(numeric_df.to_numpy()).all(axis=1)

    cat_df = frame[categorical_cols].astype(str).apply(lambda col: col.str.strip())
    non_empty_cat = (cat_df != "").all(axis=1).to_numpy(dtype=bool)

    valid = finite & non_empty_cat & has_valid_label.to_numpy(dtype=bool, na_value=False)
    if not valid.any():
        raise ValueError("No valid training records remain after schema validation.")

    clean_features = pd.concat(
        [numeric_df.loc[valid], cat_df.loc[valid]], axis=1
    )[all_features].reset_index(drop=True)
    y = mapped_labels.loc[valid].to_numpy(dtype=int)

    if len(np.unique(y)) < 2:
        raise ValueError("At least two populated target classes are required.")

    stats = {
        "input_rows": len(frame),
        "invalid_rows_removed": int((~valid).sum()),
        "invalid_label_rows": int((~has_valid_label).sum()),
        "invalid_feature_rows": int((~(finite & non_empty_cat)).sum()),
        "clean_rows": len(clean_features),
        "class_counts": {
            CLASSES[idx]: int((y == idx).sum()) for idx in range(len(CLASSES))
        },
    }
    return clean_features, y, stats


def split_data(
    features: pd.DataFrame, y: np.ndarray, config: dict
) -> tuple[pd.DataFrame, np.ndarray, pd.DataFrame, np.ndarray]:
    indices = np.arange(len(y))
    try:
        train_idx, val_idx = train_test_split(
            indices,
            test_size=config["validation_fraction"],
            random_state=config["seed"],
            stratify=y,
        )
    except ValueError as exc:
        raise ValueError(
            "Not enough samples per class for stratified train/validation split."
        ) from exc

    if len(np.unique(y[train_idx])) < 2 or len(np.unique(y[val_idx])) < 2:
        raise ValueError(
            "Both train and validation splits must contain all target classes."
        )
    return (
        features.iloc[train_idx].reset_index(drop=True),
        y[train_idx],
        features.iloc[val_idx].reset_index(drop=True),
        y[val_idx],
    )


def build_pipeline(
    numeric_cols: list[str],
    categorical_cols: list[str],
    config: dict,
) -> Pipeline:
    numeric_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipe, numeric_cols),
            ("cat", categorical_pipe, categorical_cols),
        ],
        remainder="drop",
    )
    class_weight = (
        None if config["class_weight"] in (None, "none") else config["class_weight"]
    )
    classifier = LogisticRegression(
        C=float(config["C"]),
        solver=config["solver"],
        class_weight=class_weight,
        max_iter=int(config["max_iter"]),
        random_state=int(config["seed"]),
    )
    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", classifier),
        ]
    )


class Tracking:
    """Job-scoped MLflow logger; failures downgrade gracefully to local artifacts."""

    def __init__(self):
        self.client = None
        self.run_id = None
        self.warning = None
        uri = os.environ.get("MLFLOW_TRACKING_URI", "").strip()
        if not uri:
            return
        os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] = "5"
        os.environ["MLFLOW_HTTP_REQUEST_MAX_RETRIES"] = "0"
        try:
            from mlflow.tracking import MlflowClient

            suffix = "/api/2.0/mlflow"
            sdk_uri = uri.rstrip("/").removesuffix(suffix)
            self.client = MlflowClient(tracking_uri=sdk_uri)
            run = self.client.create_run("0", tags={"mlflow.runName": "diabetes-logreg"})
            self.run_id = run.info.run_id
        except Exception as exc:
            self.disable(exc)

    def disable(self, exc: Exception) -> None:
        self.warning = (
            f"MLflow tracking disabled ({type(exc).__name__}); local JSON output remains enabled."
        )
        log("WARNING: " + self.warning)
        self.client = None

    def send(self, metrics: dict | None = None, params: dict | None = None, step: int = 0) -> None:
        if self.client is None:
            return
        try:
            from mlflow.entities import Metric, Param

            timestamp = int(time.time() * 1000)
            self.client.log_batch(
                self.run_id,
                metrics=[
                    Metric(k, float(v), timestamp, step)
                    for k, v in (metrics or {}).items()
                ],
                params=[Param(k, str(v)) for k, v in (params or {}).items()],
            )
        except Exception as exc:
            self.disable(exc)


def evaluate(
    pipeline: Pipeline,
    features: pd.DataFrame,
    y_true: np.ndarray,
    threshold: float,
) -> tuple[dict[str, float], dict]:
    y_probs = pipeline.predict_proba(features)[:, 1]
    y_pred = (y_probs >= threshold).astype(int)

    metrics = {
        "accuracy": float(round(accuracy_score(y_true, y_pred), 6)),
        "balanced_accuracy": float(round(balanced_accuracy_score(y_true, y_pred), 6)),
        "pr_auc": float(round(average_precision_score(y_true, y_probs), 6)),
        "f1": float(round(f1_score(y_true, y_pred, zero_division=0), 6)),
        "precision": float(round(precision_score(y_true, y_pred, zero_division=0), 6)),
        "recall": float(round(recall_score(y_true, y_pred, zero_division=0), 6)),
        "brier_score": float(round(brier_score_loss(y_true, y_probs), 6)),
        "threshold": float(round(threshold, 4)),
    }
    undefined = []
    try:
        roc_auc = float(roc_auc_score(y_true, y_probs))
        if math.isfinite(roc_auc):
            metrics["roc_auc"] = round(roc_auc, 6)
        else:
            undefined.append("roc_auc: non-finite")
    except ValueError:
        undefined.append("roc_auc: unavailable for this evaluation")

    p, r, f, counts = precision_recall_fscore_support(
        y_true, y_pred, labels=[0, 1], zero_division=np.nan
    )
    per_class = {}
    for index, name in enumerate(CLASSES):
        row = {"support": int(counts[index])}
        for key, value in (("precision", p[index]), ("recall", r[index]), ("f1", f[index])):
            row[key] = round(float(value), 6) if math.isfinite(value) else None
            if not math.isfinite(value):
                undefined.append(f"{name}.{key}: undefined denominator")
        per_class[name] = row

    matrix = confusion_matrix(y_true, y_pred, labels=[0, 1])
    return metrics, {
        "labels": CLASSES,
        "confusion_matrix": matrix.tolist(),
        "per_class": per_class,
        "undefined_metrics": undefined,
    }


def extract_feature_insights(
    pipeline: Pipeline, numeric_cols: list[str], categorical_cols: list[str]
) -> tuple[dict[str, float], dict]:
    preprocessor = pipeline.named_steps["preprocessor"]
    classifier = pipeline.named_steps["classifier"]

    cat_encoder = preprocessor.named_transformers_["cat"].named_steps["onehot"]
    cat_feature_names = cat_encoder.get_feature_names_out(categorical_cols).tolist()
    transformed_names = numeric_cols + cat_feature_names

    coefficients = classifier.coef_[0].tolist()
    intercept = float(classifier.intercept_[0])

    coef_pairs = [
        {
            "feature": name,
            "coefficient": round(float(coef), 5),
            "odds_ratio": round(float(np.exp(coef)), 5),
        }
        for name, coef in zip(transformed_names, coefficients)
    ]
    sorted_by_odds = sorted(coef_pairs, key=lambda x: x["odds_ratio"], reverse=True)
    importance_map = {
        name: round(abs(float(coef)), 6)
        for name, coef in zip(transformed_names, coefficients)
    }

    insights = {
        "kind": "feature_importance",
        "source": "logistic_regression_coefficients",
        "intercept": round(intercept, 5),
        "feature_count": len(numeric_cols) + len(categorical_cols),
        "total_coefficients_count": len(coefficients),
        "items": [
            {"name": name, "value": value} for name, value in importance_map.items()
        ],
        "top_positive_risk_factors": sorted_by_odds[:10],
        "top_protective_factors": sorted_by_odds[-10:][::-1],
        "all_coefficients": coef_pairs,
    }
    return importance_map, insights


def output_directory(name: str, input_root: Path) -> Path:
    value = os.environ.get(name)
    if not value:
        raise ValueError(
            f"{name} must be configured by the runner (or set for local execution)."
        )
    path = Path(value).resolve()
    if path.is_relative_to(input_root) or input_root.is_relative_to(path):
        raise ValueError(f"{name} must be separate from read-only Input.")
    path.mkdir(parents=True, exist_ok=True)
    return path


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="config.json",
        help="Configuration file inside SM_CHANNEL_TRAIN.",
    )
    args = parser.parse_args(argv)

    root = Path(os.environ.get("SM_CHANNEL_TRAIN", Path(__file__).parent)).resolve()
    config = load_config(root, args.config)
    numeric_cols, categorical_cols, all_features = load_schema(
        root, config["feature_schema"]
    )
    model_dir = output_directory("SM_MODEL_DIR", root)
    output_dir = output_directory("SM_OUTPUT_DIR", root)
    work_dir = output_directory("MLOPS_WORK_DIR", root)

    if len({model_dir, output_dir, work_dir}) != 3 or any(
        a.is_relative_to(b)
        for a in (model_dir, output_dir, work_dir)
        for b in (model_dir, output_dir, work_dir)
        if a != b
    ):
        raise ValueError("Model, Output and Work must be separate directories.")
    if any(model_dir.iterdir()):
        raise ValueError(
            "Model output directory must be empty; refusing stale artifacts."
        )
    os.chdir(work_dir)

    csv_path = input_file(root, config["train_csv"])
    log(f"Loading preprocessed Diabetes CSV from {config['train_csv']}...")
    features, y, stats = load_data(
        csv_path, numeric_cols, categorical_cols, all_features, config
    )
    train_x, train_y, val_x, val_y = split_data(features, y, config)
    log("Data preparation: " + json.dumps(stats, allow_nan=False))

    tracking = Tracking()
    versions = {
        f"version_{name}": importlib.metadata.version(name)
        for name in ("scikit-learn", "pandas", "numpy", "mlflow", "joblib")
    }
    with csv_path.open("rb") as stream:
        input_checksum = (
            hashlib.file_digest(stream, "sha256").hexdigest()
            if hasattr(hashlib, "file_digest")
            else file_sha256(stream)
        )

    params = {
        **config,
        **versions,
        "algorithm": "logistic_regression",
        "flavor": "sklearn",
        "feature_count": len(all_features),
        "numeric_feature_count": len(numeric_cols),
        "categorical_feature_count": len(categorical_cols),
        "train_rows": len(train_y),
        "validation_rows": len(val_y),
        "input_sha256": input_checksum,
    }
    tracking.send(params=params)

    log(
        f"Training LogisticRegression on train_rows={len(train_y)}, validation_rows={len(val_y)}..."
    )
    start_time = time.time()
    pipeline = build_pipeline(numeric_cols, categorical_cols, config)
    pipeline.fit(train_x, train_y)
    elapsed_seconds = round(time.time() - start_time, 2)

    metrics, evaluation = evaluate(pipeline, val_x, val_y, float(config["threshold"]))
    params["elapsed_seconds"] = elapsed_seconds
    tracking.send(params={"elapsed_seconds": elapsed_seconds}, metrics=metrics, step=1)

    model_path = model_dir / "model.joblib"
    joblib.dump(pipeline, model_path)
    restored = joblib.load(model_path)
    if not np.array_equal(
        pipeline.predict(val_x), restored.predict(val_x)
    ) or not np.allclose(
        pipeline.predict_proba(val_x),
        restored.predict_proba(val_x),
        rtol=1e-7,
        atol=1e-8,
    ):
        model_path.unlink()
        raise TrainingError("Exported model prediction parity failed.")

    importance_map, feature_insights = extract_feature_insights(
        pipeline, numeric_cols, categorical_cols
    )

    write_json(
        output_dir / "label_mapping.json",
        {str(i): label for i, label in enumerate(CLASSES)},
    )
    schema_properties = {
        **{name: {"type": "number"} for name in numeric_cols},
        **{name: {"type": "string"} for name in categorical_cols},
    }
    write_json(
        output_dir / "input_schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {name: schema_properties[name] for name in all_features},
            "required": all_features,
            "additionalProperties": False,
            "x-feature-order": all_features,
        },
    )
    write_json(output_dir / "metrics.json", metrics)
    write_json(output_dir / "params.json", params)
    write_json(
        output_dir / "feature_importance.json",
        {"feature_importance": importance_map},
    )

    report = {
        **feature_insights,
        **evaluation,
        "data_cleaning": stats,
        "splits": {
            "train": {
                "rows": len(train_y),
                "class_counts": {
                    CLASSES[i]: int((train_y == i).sum()) for i in range(len(CLASSES))
                },
            },
            "validation": {
                "rows": len(val_y),
                "class_counts": {
                    CLASSES[i]: int((val_y == i).sum()) for i in range(len(CLASSES))
                },
            },
        },
        "tracking_warning": tracking.warning,
    }
    write_json(output_dir / "model_insights.json", report)
    write_json(output_dir / "training_report.json", report)
    log("Training complete: " + json.dumps(metrics, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        if isinstance(error, (ValueError, TypeError, FileNotFoundError, TrainingError)):
            log(f"ERROR: {error}")
        else:
            log(
                f"ERROR: training failed ({type(error).__name__}). Check dependencies and available resources."
            )
        sys.exit(1)
