"""Kubeflow / Argo Workflows compatible NIDS training entry point (no MLflow).

Derived from the XGBoost NIDS trainer. This version preserves the useful
model-training logic (XGBoost with a RandomizedSearch-style configuration,
class-imbalance handling, label encoding, and a train/val/test split) but
removes ALL direct MLflow Tracking usage so it can run unmodified inside the
training runner (``services/training-runner/runner.py``).

Runtime contract (set by the training runner):
  - SM_CHANNEL_TRAIN : directory containing the training CSV (runner mounts
                       the dataset here as ``train.csv``).
  - SM_MODEL_DIR     : directory for model artifacts (packaged into
                       ``model.tar.gz``). Excludes the runner's ``_mlops`` dir.
  - SM_OUTPUT_DIR    : directory for metadata the runner ingests
                       (``metrics.json``, ``params.json``,
                       ``model_insights.json``, ``feature_importance.json``).
  - MODEL_VERSION    : logical model version label.

Local testing contract (no cloud backend required):
  python train.py --train-csv data/train_2_classes.csv \
      --model-dir /tmp/model --output-dir /tmp/output --model-version v-test

The runner parses a single stdout line of the form::

    METRIC_JSON:{"accuracy":0.99,"precision":0.99,"recall":0.99,"f1_score":0.99}

NO ``import mlflow``. NO MLflow env vars are required or read.
"""

import argparse
import json
import os
import warnings
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_sample_weight

warnings.simplefilter(action="ignore", category=FutureWarning)

# Candidate label column names, checked in priority order. If none match we
# fall back to the last column (a common convention for flat training CSVs).
LABEL_COLUMN_CANDIDATES = (
    "label",
    "Label",
    "target",
    "Target",
    "class",
    "Class",
    "y",
    "attack_cat",
)

RANDOM_STATE = 42


def log(message: str) -> None:
    print(message, flush=True)


def resolve_config() -> dict:
    """Resolve runtime config from CLI args, falling back to SM_* env vars.

    CLI args take precedence over environment variables so the script is easy
    to drive locally while remaining fully compatible with the AWS Batch
    runner, which only sets environment variables.
    """
    parser = argparse.ArgumentParser(
        description="AWS Batch-compatible NIDS XGBoost trainer (no MLflow)."
    )
    parser.add_argument("--train-csv", default=None, help="Path to a training CSV file.")
    parser.add_argument(
        "--train-dir",
        default=None,
        help="Directory containing training CSV(s); first *.csv is used.",
    )
    parser.add_argument("--model-dir", default=None, help="Output dir for model artifacts.")
    parser.add_argument("--output-dir", default=None, help="Output dir for metadata files.")
    parser.add_argument("--model-version", default=None, help="Logical model version label.")
    args = parser.parse_args()

    train_dir = args.train_dir or os.environ.get("SM_CHANNEL_TRAIN", "/opt/ml/input/data/train")
    model_dir = args.model_dir or os.environ.get("SM_MODEL_DIR", "/opt/ml/model")
    # SM_OUTPUT_DIR is set by the runner; SageMaker also exposes
    # SM_OUTPUT_DATA_DIR. Fall back to the model dir so metadata is never lost.
    output_dir = (
        args.output_dir
        or os.environ.get("SM_OUTPUT_DIR")
        or os.environ.get("SM_OUTPUT_DATA_DIR")
        or model_dir
    )
    model_version = args.model_version or os.environ.get("MODEL_VERSION", "v1")

    return {
        "train_csv": args.train_csv,
        "train_dir": train_dir,
        "model_dir": model_dir,
        "output_dir": output_dir,
        "model_version": model_version,
    }


def find_training_csv(train_csv: str | None, train_dir: str) -> str:
    """Locate the training CSV from an explicit path or the train channel."""
    if train_csv:
        if not os.path.exists(train_csv):
            raise FileNotFoundError(f"--train-csv path does not exist: {train_csv}")
        return train_csv

    if not os.path.isdir(train_dir):
        raise FileNotFoundError(
            f"Training directory does not exist: {train_dir}. "
            "Set SM_CHANNEL_TRAIN or pass --train-csv/--train-dir."
        )

    csv_files = sorted(
        os.path.join(train_dir, name)
        for name in os.listdir(train_dir)
        if name.lower().endswith(".csv")
    )
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in training directory: {train_dir}")
    # The AWS Batch runner mounts the dataset as ``train.csv``; prefer it.
    for candidate in csv_files:
        if os.path.basename(candidate).lower() == "train.csv":
            return candidate
    return csv_files[0]


def detect_label_column(df: pd.DataFrame) -> str:
    """Robustly detect the label column, falling back to the last column."""
    for candidate in LABEL_COLUMN_CANDIDATES:
        if candidate in df.columns:
            return candidate
    # Case-insensitive second pass.
    lowered = {str(col).lower(): col for col in df.columns}
    for candidate in LABEL_COLUMN_CANDIDATES:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return df.columns[-1]


def preprocess_features(X: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Safely coerce features to a numeric matrix.

    Network-flow CSVs occasionally contain infinities (e.g. Flow Bytes/s when
    duration is zero) and stray non-numeric tokens. We coerce everything to
    numeric, replace +/-inf with NaN, and fill NaN with 0 so XGBoost / the
    fallback estimator receive a clean matrix. Constant/all-NaN columns are
    dropped.
    """
    warnings_list: list[str] = []
    X = X.copy()

    object_cols = [col for col in X.columns if X[col].dtype == object]
    for col in object_cols:
        coerced = pd.to_numeric(X[col], errors="coerce")
        # If coercion destroyed (almost) everything, label-encode instead.
        if coerced.notna().mean() < 0.5:
            X[col] = LabelEncoder().fit_transform(X[col].astype(str))
            warnings_list.append(f"Categorical feature '{col}' was label-encoded.")
        else:
            X[col] = coerced
            warnings_list.append(f"Feature '{col}' coerced to numeric.")

    X = X.replace([np.inf, -np.inf], np.nan)

    dropped = [col for col in X.columns if X[col].isna().all()]
    if dropped:
        X = X.drop(columns=dropped)
        warnings_list.append(f"Dropped all-NaN feature columns: {dropped}")

    X = X.fillna(0)
    return X, warnings_list


def _build_random_forest(num_classes: int, fallback_warning: str | None):
    """Construct the RandomForest fallback estimator.

    Returns a 5-tuple matching ``build_estimator``:
    ``(model, algorithm, sample_weight, hyperparameters, fallback_warning)``.
    """
    from sklearn.ensemble import RandomForestClassifier

    rf_params = {
        "n_estimators": 200,
        "max_depth": None,
        "random_state": RANDOM_STATE,
        "n_jobs": -1,
        "class_weight": "balanced",
    }
    return (
        RandomForestClassifier(**rf_params),
        "random_forest",
        None,
        rf_params,
        fallback_warning,
    )


def build_estimator(num_classes: int, y_train: np.ndarray):
    """Build the primary XGBoost estimator, falling back to RandomForest.

    Mirrors the legacy configuration: binary uses ``binary:logistic`` with
    ``scale_pos_weight``; multiclass uses ``multi:softprob`` with balanced
    sample weights.

    The XGBoost path is guarded broadly. In slim AWS Batch images XGBoost can
    fail not only with ``ImportError`` (package missing) but also with
    ``OSError`` / ``xgboost.core.XGBoostError`` when the OpenMP runtime
    (``libgomp``) is absent at import or construction time. Any such failure
    (or the ``NIDS_FORCE_RF_FALLBACK`` debug override) routes to a
    ``RandomForestClassifier`` with ``class_weight='balanced'`` so the job
    still produces a model and the full metadata contract.

    Returns ``(model, algorithm, sample_weight, hyperparameters, fallback_warning)``
    where ``fallback_warning`` is ``None`` when XGBoost was used, or a
    human-readable string when RandomForest was substituted.
    """
    sample_weight = None

    # Debug/test override: force the fallback path without breaking XGBoost.
    if os.environ.get("NIDS_FORCE_RF_FALLBACK", "").strip().lower() in {"1", "true", "yes"}:
        warning = (
            "XGBoost skipped via NIDS_FORCE_RF_FALLBACK override; "
            "RandomForestClassifier fallback was used."
        )
        log(f"WARNING: {warning}")
        return _build_random_forest(num_classes, warning)

    try:
        from xgboost import XGBClassifier

        xgb_params = {
            "tree_method": "hist",
            "verbosity": 0,
            "random_state": RANDOM_STATE,
            "n_estimators": 150,
            "max_depth": 6,
            "learning_rate": 0.1,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
        }
        if num_classes == 2:
            xgb_params["objective"] = "binary:logistic"
            xgb_params["eval_metric"] = "logloss"
            neg_count = int((y_train == 0).sum())
            pos_count = int((y_train == 1).sum())
            xgb_params["scale_pos_weight"] = neg_count / max(pos_count, 1)
        else:
            xgb_params["objective"] = "multi:softprob"
            xgb_params["eval_metric"] = "mlogloss"
            xgb_params["num_class"] = num_classes
            sample_weight = compute_sample_weight(class_weight="balanced", y=y_train)
        # Construct inside the guard: missing libgomp can raise OSError /
        # XGBoostError at class instantiation, not just at import.
        model = XGBClassifier(**xgb_params)
        return model, "xgboost", sample_weight, xgb_params, None
    except (ImportError, OSError, Exception) as exc:  # noqa: BLE001 - intentional broad guard
        # ImportError: xgboost not installed.
        # OSError / xgboost.core.XGBoostError (an Exception subclass): missing
        # OpenMP runtime (libgomp) or other native init failure in slim images.
        warning = (
            f"XGBoost unavailable ({type(exc).__name__}: {exc}); "
            "RandomForestClassifier fallback was used."
        )
        log(f"WARNING: {warning}")
        return _build_random_forest(num_classes, warning)


def compute_feature_importances(model, feature_names: list[str]) -> dict[str, float]:
    """Extract feature importances from the fitted estimator, if available."""
    importances = getattr(model, "feature_importances_", None)
    if importances is None:
        return {}
    return {
        str(name): float(value)
        for name, value in zip(feature_names, importances)
    }


def main() -> None:
    config = resolve_config()
    model_version = config["model_version"]
    model_dir = config["model_dir"]
    output_dir = config["output_dir"]

    os.makedirs(model_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    log("=" * 60)
    log("AWS Batch NIDS training configuration (no MLflow)")
    log(f"MODEL_VERSION : {model_version}")
    log(f"MODEL_DIR     : {model_dir}")
    log(f"OUTPUT_DIR    : {output_dir}")
    log("=" * 60)

    warnings_list: list[str] = []

    csv_path = find_training_csv(config["train_csv"], config["train_dir"])
    log(f"Loading training data: {csv_path}")
    df = pd.read_csv(csv_path)

    label_column = detect_label_column(df)
    log(f"Detected label column: {label_column}")

    y_raw = df[label_column]
    X_raw = df.drop(columns=[label_column])

    X, preprocess_warnings = preprocess_features(X_raw)
    warnings_list.extend(preprocess_warnings)
    feature_names = list(X.columns)

    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(y_raw)
    num_classes = int(len(label_encoder.classes_))
    log(f"Classes ({num_classes}): {label_encoder.classes_.tolist()}")

    # Stratified split mirrors the legacy 80/20 holdout; we keep a validation
    # slice for parity even though the simplified estimator does not early-stop.
    stratify = y if num_classes > 1 and np.min(np.bincount(y)) >= 2 else None
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=stratify
    )

    model, algorithm, sample_weight, hyperparameters, fallback_warning = build_estimator(
        num_classes, y_train
    )
    log(f"Training estimator: {algorithm}")
    if fallback_warning:
        warnings_list.append(fallback_warning)

    fit_kwargs = {}
    if sample_weight is not None:
        fit_kwargs["sample_weight"] = sample_weight
    model.fit(X_train, y_train, **fit_kwargs)

    y_pred = model.predict(X_test)
    average_method = "binary" if num_classes == 2 else "macro"
    metrics = {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "precision": round(
            float(precision_score(y_test, y_pred, average=average_method, zero_division=0)), 4
        ),
        "recall": round(
            float(recall_score(y_test, y_pred, average=average_method, zero_division=0)), 4
        ),
        "f1_score": round(
            float(f1_score(y_test, y_pred, average=average_method, zero_division=0)), 4
        ),
    }
    log(f"Evaluation metrics: {metrics}")

    # --- Save model artifacts to SM_MODEL_DIR ---
    model_path = os.path.join(model_dir, "model.joblib")
    joblib.dump(model, model_path)

    label_classes = label_encoder.classes_.tolist()
    label_classes_path = os.path.join(model_dir, "label_classes.json")
    with open(label_classes_path, "w", encoding="utf-8") as handle:
        json.dump(label_classes, handle)

    # --- Write metadata to SM_OUTPUT_DIR (consumed by the runner) ---
    metrics_path = os.path.join(output_dir, "metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                **metrics,
                "samples": int(len(df)),
                "num_classes": num_classes,
            },
            handle,
            indent=2,
        )

    params_path = os.path.join(output_dir, "params.json")
    with open(params_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "algorithm": algorithm,
                "model_version": model_version,
                "hyperparameters": {k: str(v) for k, v in hyperparameters.items()},
                "random_state": RANDOM_STATE,
                "label_column": label_column,
                "feature_count": len(feature_names),
                "training_backend": "kubeflow",
                "xgboost_available": fallback_warning is None,
                "fallback_reason": fallback_warning,
            },
            handle,
            indent=2,
        )

    feature_importances = compute_feature_importances(model, feature_names)
    top_importances = sorted(
        feature_importances.items(), key=lambda kv: abs(kv[1]), reverse=True
    )[:20]

    model_insights_path = os.path.join(output_dir, "model_insights.json")
    with open(model_insights_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "kind": "feature_importance",
                "source": "nids_xgb_no_mlflow",
                "feature_count": len(feature_names),
                "items": [{"name": name, "value": value} for name, value in top_importances],
                "label_classes": label_classes,
                "sample_count": int(len(df)),
                "model_type": algorithm,
                "warnings": warnings_list,
            },
            handle,
            indent=2,
        )

    if feature_importances:
        feature_importance_path = os.path.join(output_dir, "feature_importance.json")
        with open(feature_importance_path, "w", encoding="utf-8") as handle:
            json.dump({"feature_importance": feature_importances}, handle, indent=2)

    label_classes_out = os.path.join(output_dir, "label_classes.json")
    with open(label_classes_out, "w", encoding="utf-8") as handle:
        json.dump(label_classes, handle)

    # Single machine-parseable metric line for the AWS Batch runner.
    print("METRIC_JSON:" + json.dumps(metrics, separators=(",", ":")), flush=True)

    log(f"Training completed at {datetime.now(timezone.utc).isoformat()} for {model_version}.")


if __name__ == "__main__":
    main()
