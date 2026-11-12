"""CICIDS2017 (52 numeric features) trainer for job-owned MLOps workspaces."""

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_sample_weight

DEFAULTS = {
    "train_csv": "data/train.csv",
    "feature_schema": "feature_schema.json",
    "classification_mode": "binary",
    "label_column": "Label",
    "seed": 42,
    "validation_fraction": 0.15,
    "test_fraction": 0.15,
    "device": "auto",
    "max_threads": None,
    "n_estimators": 500,
    "early_stopping_rounds": 30,
    "max_depth": 6,
    "learning_rate": 0.1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
}


class TrainingError(RuntimeError):
    """A safe, actionable failure for the training terminal."""


def log(message):
    print(message, flush=True)


def write_json(path, payload):
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def file_sha256(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def input_file(root, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Input paths must be non-empty strings.")
    path = (root / value).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"Input must be an existing file inside Input: {value}")
    return path


def load_config(root, config_path):
    supplied = json.loads(input_file(root, config_path).read_text(encoding="utf-8"))
    if not isinstance(supplied, dict) or set(supplied) - set(DEFAULTS):
        raise ValueError(
            "config.json must be an object containing only documented options."
        )
    config = {**DEFAULTS, **supplied}
    if not isinstance(config["classification_mode"], str) or config[
        "classification_mode"
    ] not in {"binary", "multiclass"}:
        raise ValueError("classification_mode must be binary or multiclass.")
    if not isinstance(config["device"], str) or config["device"] not in {
        "auto",
        "cpu",
        "cuda",
    }:
        raise ValueError("device must be auto, cpu or cuda.")
    if (
        not isinstance(config["label_column"], str)
        or not config["label_column"].strip()
    ):
        raise ValueError("label_column is required.")
    config["label_column"] = config["label_column"].strip()
    for key in (
        "seed",
        "n_estimators",
        "early_stopping_rounds",
        "max_depth",
        "max_threads",
    ):
        value = config[key]
        if key == "max_threads" and value is None:
            continue
        if type(value) is not int or value < (0 if key == "seed" else 1):
            raise ValueError(f"{key} must be a positive integer (seed may be zero).")
    for key in (
        "validation_fraction",
        "test_fraction",
        "learning_rate",
        "subsample",
        "colsample_bytree",
    ):
        value = config[key]
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not 0 < value <= 1
        ):
            raise ValueError(f"Invalid fraction/rate: {key}")
    if config["validation_fraction"] + config["test_fraction"] >= 1:
        raise ValueError(
            "Validation and test fractions must leave a training partition."
        )
    if config["seed"] > np.iinfo(np.uint32).max:
        raise ValueError("seed must fit an unsigned 32-bit integer.")
    return config


def load_schema(root, filename):
    names = json.loads(input_file(root, filename).read_text(encoding="utf-8"))
    if (
        not isinstance(names, list)
        or len(names) != 52
        or any(not isinstance(n, str) or not n.strip() or n != n.strip() for n in names)
        or len(set(names)) != 52
    ):
        raise ValueError(
            "feature_schema.json must list 52 distinct, trimmed feature names."
        )
    return names


def load_data(path, names, config):
    # Check before pandas mangles duplicate headers into distinct names.
    with path.open(encoding="utf-8-sig", newline="") as stream:
        header = next(csv.reader(stream), [])
    columns = [c.strip() for c in header]
    label = config["label_column"]
    if len(set(columns)) != len(columns):
        raise ValueError("Duplicate CSV columns after trimming whitespace.")
    expected = set(names) | {label}
    if label in names or set(columns) != expected:
        raise ValueError(
            f"CSV schema mismatch: missing={sorted(expected - set(columns))}, extra={sorted(set(columns) - expected)}"
        )
    frame = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    frame.columns = columns
    raw_labels = frame[label].astype("string").str.strip()
    features = frame[names].apply(pd.to_numeric, errors="coerce").astype("float64")
    # XGBoost uses float32 internally; huge finite doubles must not become infinity.
    finite = np.isfinite(features.to_numpy()).all(axis=1)
    finite &= (features.abs() <= np.finfo(np.float32).max).all(axis=1).to_numpy()
    has_label = raw_labels.notna() & raw_labels.ne("")
    valid = finite & has_label.to_numpy(dtype=bool, na_value=False)
    clean = features.loc[valid].copy()
    labels = raw_labels.loc[valid].astype(str)
    if config["classification_mode"] == "binary":
        benign = labels.str.upper().isin({"BENIGN", "NORMAL"})
        labels = pd.Series(np.where(benign, "BENIGN", "ATTACK"), index=labels.index)
        classes = ["BENIGN", "ATTACK"]
    else:
        classes = sorted(labels.unique().tolist())
    # Exact feature identity (including +0/-0 equivalence), not label+features.
    conflict = (
        clean.assign(__label=labels).groupby(names, dropna=False)["__label"].nunique()
    )
    if (conflict > 1).any():
        raise ValueError("Identical feature vectors have conflicting target labels.")
    duplicates = clean.duplicated(keep="first")
    clean, labels = clean.loc[~duplicates], labels.loc[~duplicates]
    mapping = {name: index for index, name in enumerate(classes)}
    y = labels.map(mapping).to_numpy(dtype=int)
    if len(classes) < 2 or len(np.unique(y)) != len(classes):
        raise ValueError("At least two populated target classes are required.")
    stats = {
        "input_rows": len(frame),
        "invalid_rows_removed": int((~valid).sum()),
        "missing_label_rows": int((~has_label.fillna(False)).sum()),
        "invalid_feature_rows": int((~finite).sum()),
        "duplicate_rows_removed": int(duplicates.sum()),
        "clean_rows": len(clean),
        "class_counts": {name: int((labels == name).sum()) for name in classes},
    }
    return clean.reset_index(drop=True), y, classes, stats


def split_data(features, y, config):
    indices = np.arange(len(y))
    try:
        remaining, test = train_test_split(
            indices,
            test_size=config["test_fraction"],
            random_state=config["seed"],
            stratify=y,
        )
        train, validation = train_test_split(
            remaining,
            test_size=math.ceil(len(y) * config["validation_fraction"]),
            random_state=config["seed"],
            stratify=y[remaining],
        )
    except ValueError as exc:
        raise ValueError(
            "Not enough samples per class for stratified train/validation/test splits."
        ) from exc
    parts = {"train": train, "validation": validation, "test": test}
    if any(len(np.unique(y[part])) != len(np.unique(y)) for part in parts.values()):
        raise ValueError(
            "Each split must contain every target class; supply more samples."
        )
    return {name: (features.iloc[part], y[part]) for name, part in parts.items()}


def cpu_threads(requested=None, cgroup_root=Path("/sys/fs/cgroup")):
    limits = [os.cpu_count() or 1]
    if hasattr(os, "sched_getaffinity"):
        limits.append(len(os.sched_getaffinity(0)))
    try:
        quota, period = (cgroup_root / "cpu.max").read_text().split()
        if quota != "max":
            limits.append(max(1, math.floor(int(quota) / int(period))))
    except (OSError, ValueError, ZeroDivisionError):
        pass
    for folder in (cgroup_root / "cpu", cgroup_root / "cpu,cpuacct", cgroup_root):
        try:
            quota = int((folder / "cpu.cfs_quota_us").read_text())
            period = int((folder / "cpu.cfs_period_us").read_text())
            if quota > 0:
                limits.append(max(1, math.floor(quota / period)))
        except (OSError, ValueError, ZeroDivisionError):
            continue
    if requested is not None:
        limits.append(requested)
    return max(1, min(limits))


def select_device(requested):
    if requested == "cpu":
        return "cpu"
    executable = shutil.which("nvidia-smi")
    if executable is None:
        if requested == "cuda":
            raise TrainingError("CUDA requested but NVIDIA tooling is unavailable.")
        return "cpu"
    try:
        result = subprocess.run(
            [executable, "--query-gpu=uuid", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TrainingError(
            "NVIDIA probe failed; select CPU explicitly if intended."
        ) from exc
    output = result.stdout.strip()
    # Some CPU nodes expose the executable/driver without any devices.
    if "no devices were found" in (output + result.stderr).lower():
        output = ""
    elif result.returncode:
        raise TrainingError("NVIDIA probe failed; refusing an implicit CPU fallback.")
    devices = output.splitlines() if output else []
    if len(devices) > 1:
        raise TrainingError(
            "Expected at most one GPU visible to the training container."
        )
    if not devices and requested == "cuda":
        raise TrainingError("CUDA requested but no GPU is visible.")
    return "cuda" if devices else "cpu"


class Tracking:
    """Only supported job-scoped MLflow calls; no fluent/global run lifecycle."""

    def __init__(self):
        self.client = None
        self.run_id = None
        self.warning = None
        uri = os.environ.get("MLFLOW_TRACKING_URI", "").strip()
        if not uri:
            return
        # Bound the first failure as well as avoiding further calls after it.
        os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] = "5"
        os.environ["MLFLOW_HTTP_REQUEST_MAX_RETRIES"] = "0"
        try:
            from mlflow.tracking import MlflowClient

            # Runtime supplies the REST prefix; the SDK appends this prefix itself.
            suffix = "/api/2.0/mlflow"
            sdk_uri = uri.rstrip("/")
            sdk_uri = sdk_uri.removesuffix(suffix)
            self.client = MlflowClient(tracking_uri=sdk_uri)
            # Control Plane maps create_run to the authenticated job, not a new job.
            run = self.client.create_run("0", tags={"mlflow.runName": "nids-xgboost"})
            self.run_id = run.info.run_id
        except Exception as exc:  # noqa: BLE001 - optional tracking must not abort training
            self.disable(exc)

    def disable(self, exc):
        self.warning = f"MLflow tracking disabled ({type(exc).__name__}); local JSON output remains enabled."
        log("WARNING: " + self.warning)
        self.client = None

    def send(self, metrics=None, params=None, step=0):
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
        except Exception as exc:  # noqa: BLE001 - disable all further tracking after a failure
            self.disable(exc)


def booster_device(booster):
    return json.loads(booster.save_config())["learner"]["generic_param"]["device"]


class Progress(xgb.callback.TrainingCallback):
    def __init__(self, tracking, device):
        self.tracking, self.device = tracking, device
        self.history = {}

    def after_iteration(self, model, epoch, evals_log):
        if self.device == "cuda" and not booster_device(model).startswith("cuda"):
            raise TrainingError("XGBoost fell back from CUDA to CPU; training aborted.")
        values = {}
        for partition, metrics in evals_log.items():
            for name, series in metrics.items():
                partition_name = {
                    "validation_0": "train",
                    "validation_1": "validation",
                }.get(partition, partition)
                key = f"{partition_name}_{name}"
                value = float(series[-1])
                if not math.isfinite(value):
                    raise TrainingError("Non-finite validation/training loss.")
                self.history.setdefault(key, []).append(value)
                values[key] = value
        self.tracking.send(metrics=values, step=epoch)
        if epoch % 10 == 0:
            log(f"Round {epoch}: " + json.dumps(values, allow_nan=False))
        return False


def evaluate(model, features, y, classes):
    predicted = model.predict(features)
    probabilities = model.predict_proba(features)
    metrics = {"accuracy": float(accuracy_score(y, predicted))}
    undefined = []
    for average in ("macro", "weighted"):
        precision, recall, f1, _ = precision_recall_fscore_support(
            y,
            predicted,
            labels=np.arange(len(classes)),
            average=average,
            zero_division=np.nan,
        )
        for name, value in (("precision", precision), ("recall", recall), ("f1", f1)):
            if math.isfinite(value):
                metrics[f"{name}_{average}"] = float(value)
            else:
                undefined.append(f"{name}_{average}: undefined denominator")
    p, r, f, counts = precision_recall_fscore_support(
        y,
        predicted,
        labels=np.arange(len(classes)),
        zero_division=np.nan,
    )
    report = {}
    for index, name in enumerate(classes):
        row = {"support": int(counts[index])}
        for key, value in (
            ("precision", p[index]),
            ("recall", r[index]),
            ("f1", f[index]),
        ):
            row[key] = float(value) if math.isfinite(value) else None
            if not math.isfinite(value):
                undefined.append(f"{name}.{key}: undefined denominator")
        report[name] = row
    matrix = confusion_matrix(y, predicted, labels=np.arange(len(classes)))
    if classes == ["BENIGN", "ATTACK"]:
        tn, fp, fn, tp = matrix.ravel()
        metrics.update(
            attack_recall=float(tp / (tp + fn)), benign_fpr=float(fp / (tn + fp))
        )
    try:
        auc = (
            roc_auc_score(y, probabilities[:, 1])
            if len(classes) == 2
            else roc_auc_score(
                y,
                probabilities,
                labels=np.arange(len(classes)),
                multi_class="ovr",
                average="macro",
            )
        )
        if math.isfinite(auc):
            metrics["roc_auc"] = float(auc)
        else:
            undefined.append("roc_auc: non-finite")
    except ValueError:
        undefined.append("roc_auc: unavailable for this evaluation")
    return metrics, {
        "labels": classes,
        "confusion_matrix": matrix.tolist(),
        "per_class": report,
        "undefined_metrics": undefined,
    }


def output_directory(name, input_root):
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="config.json",
        help="Configuration file inside SM_CHANNEL_TRAIN.",
    )
    args = parser.parse_args(argv)
    root = Path(os.environ.get("SM_CHANNEL_TRAIN", Path(__file__).parent)).resolve()
    config = load_config(root, args.config)
    names = load_schema(root, config["feature_schema"])
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
    log("Loading CICIDS2017 CSV and validating 52 numeric features.")
    features, labels, classes, stats = load_data(csv_path, names, config)
    parts = split_data(features, labels, config)
    log("Data preparation: " + json.dumps(stats, allow_nan=False))
    device = select_device(config["device"])
    threads = cpu_threads(config["max_threads"])
    tracking = Tracking()
    progress = Progress(tracking, device)
    objective = "binary:logistic" if len(classes) == 2 else "multi:softprob"
    parameters = {
        key: config[key]
        for key in (
            "n_estimators",
            "max_depth",
            "learning_rate",
            "subsample",
            "colsample_bytree",
            "early_stopping_rounds",
        )
    }
    parameters.update(
        tree_method="hist",
        device=device,
        n_jobs=threads,
        random_state=config["seed"],
        objective=objective,
        eval_metric="logloss" if len(classes) == 2 else "mlogloss",
    )
    if len(classes) > 2:
        parameters["num_class"] = len(classes)
    versions = {
        f"version_{name}": importlib.metadata.version(name)
        for name in ("xgboost", "scikit-learn", "pandas", "numpy", "mlflow")
    }
    with csv_path.open("rb") as stream:
        input_checksum = (
            hashlib.file_digest(stream, "sha256").hexdigest()
            if hasattr(hashlib, "file_digest")
            else file_sha256(stream)
        )
    params = {
        **config,
        **{k: v for k, v in parameters.items()},
        **versions,
        "algorithm": "xgboost",
        "weighting": "balanced_train_only",
        "num_classes": len(classes),
        "feature_count": len(names),
        "input_sha256": input_checksum,
    }
    params.update({f"{name}_rows": len(values[1]) for name, values in parts.items()})
    params["max_threads"] = threads
    tracking.send(params=params)
    log(
        f"Training XGBoost on {device}, threads={threads}, rows={stats['clean_rows']}, classes={classes}"
    )
    model = xgb.XGBClassifier(**parameters, callbacks=[progress])
    train_x, train_y = parts["train"]
    validation_x, validation_y = parts["validation"]
    model.fit(
        train_x,
        train_y,
        sample_weight=compute_sample_weight("balanced", train_y),
        eval_set=[(train_x, train_y), (validation_x, validation_y)],
        verbose=False,
    )
    best, best_score = model.best_iteration, model.best_score
    # Slicing physically removes post-best trees, including their stale attributes.
    model._Booster = model.get_booster()[: best + 1]
    model._Booster.set_attr(best_iteration=str(best), best_score=str(best_score))
    model.set_params(device="cpu", callbacks=None, early_stopping_rounds=None)
    model.get_booster().set_param({"device": "cpu", "nthread": threads})
    test_x, test_y = parts["test"]
    metrics, evaluation = evaluate(model, test_x, test_y, classes)
    params.update(
        best_iteration=best, exported_rounds=model.get_booster().num_boosted_rounds()
    )
    tracking.send(params={k: params[k] for k in ("best_iteration", "exported_rounds")})
    tracking.send(metrics=metrics, step=best)
    importances = model.get_booster().get_score(importance_type="gain")
    importance = {name: float(importances.get(name, 0)) for name in names}
    model_path = model_dir / "model.joblib"
    joblib.dump(model, model_path)
    restored = joblib.load(model_path)
    if not np.array_equal(
        model.predict(test_x), restored.predict(test_x)
    ) or not np.allclose(
        model.predict_proba(test_x),
        restored.predict_proba(test_x),
        rtol=1e-7,
        atol=1e-8,
    ):
        model_path.unlink()
        raise TrainingError("Exported model prediction parity failed.")
    write_json(
        output_dir / "label_mapping.json",
        {str(i): name for i, name in enumerate(classes)},
    )
    write_json(
        output_dir / "input_schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {name: {"type": "number"} for name in names},
            "required": names,
            "additionalProperties": False,
            "x-feature-order": names,
        },
    )
    write_json(output_dir / "metrics.json", metrics)
    write_json(output_dir / "params.json", params)
    write_json(
        output_dir / "feature_importance.json", {"feature_importance": importance}
    )
    insights = {
        "kind": "feature_importance",
        "source": "xgboost_gain",
        "feature_count": len(names),
        "items": [{"name": name, "value": value} for name, value in importance.items()],
        **evaluation,
        "data_cleaning": stats,
        "splits": {
            name: {
                "rows": len(y),
                "class_counts": {
                    classes[i]: int((y == i).sum()) for i in range(len(classes))
                },
            }
            for name, (_, y) in parts.items()
        },
        "learning_curves": progress.history,
        "tracking_warning": tracking.warning,
        "evaluation_protocol": "Stratified random holdout, one fit; not temporal validation or the frozen research experiment.",
    }
    write_json(output_dir / "model_insights.json", insights)
    # Runner normalizes insight items; preserve detailed evidence in the archive too.
    write_json(output_dir / "training_report.json", insights)
    log("Training complete: " + json.dumps(metrics, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001 - CLI boundary redacts HTTP/capability details
        # Never print HTTP exception details: they can contain capability URLs/tokens.
        if isinstance(error, (ValueError, FileNotFoundError, TrainingError)):
            log(f"ERROR: {error}")
        else:
            log(
                f"ERROR: training failed ({type(error).__name__}). Check dependencies, CUDA and available resources."
            )
        sys.exit(1)
