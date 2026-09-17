"""Framework-independent tabular inference operations."""

from typing import Any

import numpy as np
import pandas as pd


def _map_label(value: Any, label_mapping: dict | None) -> Any:
    if label_mapping is None:
        return value
    string_value = str(value)
    if value in label_mapping:
        return label_mapping[value]
    if string_value in label_mapping:
        return label_mapping[string_value]
    if type(value) in (int, float) and int(value) in label_mapping:
        return label_mapping[int(value)]
    return value


def _prediction_confidence(model: Any, frame: pd.DataFrame) -> float | None:
    try:
        raw_model = getattr(model, "_model_impl", None)
        if not raw_model and hasattr(model, "unwrap_python_model"):
            raw_model = model.unwrap_python_model()
        if not hasattr(raw_model, "predict_proba"):
            return None
        probabilities = raw_model.predict_proba(frame)
        if hasattr(probabilities, "tolist"):
            probabilities = probabilities.tolist()
        if isinstance(probabilities, list) and probabilities:
            return round(max(probabilities[0]) * 100, 2)
    except Exception:
        return None
    return None


def run_inference(loaded_model: dict[str, Any], features: dict[str, Any]) -> tuple[Any, float | None]:
    model = loaded_model["model"]
    expected_features = loaded_model.get("expected_features")
    if expected_features:
        missing = set(expected_features) - set(features)
        if missing:
            raise KeyError(tuple(sorted(missing)))

    frame = pd.DataFrame([features])
    if expected_features:
        frame = frame[expected_features]
    prediction = model.predict(frame)
    if isinstance(prediction, (np.ndarray, pd.Series)):
        result = prediction.tolist()
    else:
        result = prediction if isinstance(prediction, list) else [prediction]

    value = result[0] if result else result
    while isinstance(value, list) and value:
        value = value[0]
    value = _map_label(value, loaded_model.get("label_mapping"))
    return value, _prediction_confidence(model, frame)
