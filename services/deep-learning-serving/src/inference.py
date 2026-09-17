"""Framework-independent deep-learning input and output normalization."""

from typing import Any

import pandas as pd


def input_frame(payload: Any) -> tuple[pd.DataFrame, str]:
    features = payload.get("features", payload) if isinstance(payload, dict) else payload
    model_version_id = (
        payload.get("model_version_id")
        if isinstance(payload, dict)
        else None
    )
    if isinstance(features, dict):
        if all(isinstance(value, (list, tuple, pd.Series)) for value in features.values()):
            frame = pd.DataFrame(features)
        else:
            frame = pd.DataFrame([features])
    elif isinstance(features, list):
        frame = pd.DataFrame(features)
    elif isinstance(features, pd.DataFrame):
        frame = features
    else:
        frame = pd.DataFrame(features)
    return frame, str(model_version_id or "unknown")


def run_inference(model: Any, payload: Any) -> tuple[Any, str]:
    frame, model_version_id = input_frame(payload)
    predictions = model.predict(frame)
    result = predictions.tolist() if hasattr(predictions, "tolist") else list(predictions)
    prediction = result[0] if isinstance(result, list) and len(result) == 1 else result
    return prediction, model_version_id
