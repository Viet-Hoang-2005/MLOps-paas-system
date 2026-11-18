"""Run Evidently and translate its results to the Monitoring report contract."""

from importlib.metadata import version
from math import isfinite

import numpy as np
import pandas as pd
from evidently import Dataset, Report
from evidently.metrics import ValueDrift
from evidently.presets import DataDriftPreset


def build_report(reference, current, feature_columns, definition, prediction, threshold):
    columns = [*feature_columns, prediction] if prediction else feature_columns
    metrics = []
    if feature_columns:
        metrics.append(DataDriftPreset(columns=feature_columns, drift_share=threshold))
    if prediction:
        metrics.append(ValueDrift(column=prediction))

    snapshot = None
    results = []
    if columns:
        snapshot = Report(metrics, include_tests=True).run(
            current_data=Dataset.from_pandas(current[columns], data_definition=definition),
            reference_data=Dataset.from_pandas(reference[columns], data_definition=definition),
        )
        results = snapshot.dict()["metrics"]

    rows = {}
    for result in snapshot.metric_results.values() if snapshot else ():
        config = result.get_metric_value_location().metric.params
        column = config.get("column")
        if config.get("type", "").rsplit(":", 1)[-1] != "ValueDrift" or column not in columns:
            continue
        test = next((test for test in result.tests if test.id == "drift"), None)
        if test is None or test.status.value not in {"SUCCESS", "FAIL"}:
            raise ValueError(f"Evidently returned no drift decision for {column!r}.")
        if not isfinite(result.value) or not isfinite(config["threshold"]):
            raise ValueError(f"Evidently returned non-finite drift statistics for {column!r}.")
        numerical = column in definition.numerical_columns
        current_hist, reference_hist = distributions(current[column], reference[column], numerical)
        rows[column] = {
            "column_name": column,
            "column_type": "num" if numerical else "cat",
            "stattest_name": config["method"],
            "stattest_threshold": config["threshold"],
            "drift_score": result.value,
            "drift_detected": test.status.value == "FAIL",
            "current": current_hist,
            "reference": reference_hist,
        }
    if missing := set(columns) - rows.keys():
        raise ValueError(f"Evidently returned no metrics for {', '.join(sorted(missing))}.")
    report = {
        "schema_version": 2,
        "evidently_version": version("evidently"),
        "columns": [rows[column] for column in columns],
        "evidently_metrics": results,
    }
    return snapshot, report, rows


def distributions(current, reference, numerical):
    """Provide the same chart inputs to the UI for both windows."""
    if numerical:
        current_values = pd.to_numeric(current, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
        reference_values = pd.to_numeric(reference, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
        current_values = current_values[np.isfinite(current_values)]
        reference_values = reference_values[np.isfinite(reference_values)]
        edges = np.histogram_bin_edges(np.concatenate((current_values, reference_values)), bins=10)
        if not np.isfinite(edges).all() or not (np.diff(edges) > 0).all():
            return {}, {}
        current_counts = np.histogram(current_values, bins=edges, density=True)[0]
        reference_counts = np.histogram(reference_values, bins=edges, density=True)[0]
        return distribution(edges, current_counts), distribution(edges, reference_counts)

    current_counts = current.dropna().map(str).value_counts()
    reference_counts = reference.dropna().map(str).value_counts()
    return (
        distribution(current_counts.index, current_counts),
        distribution(reference_counts.index, reference_counts),
    )


def distribution(labels, values):
    if not np.isfinite(values).all():
        return {}
    return {"small_distribution": {"x": labels.tolist(), "y": values.tolist()}}
