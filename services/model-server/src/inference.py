"""Framework-independent interpretation of serving-worker responses."""

from typing import Any

from src.routing import serving_engine_for_flavor


def parse_worker_prediction(
    data: Any,
    model_flavor: Any,
) -> tuple[Any, float | None, str]:
    if isinstance(data, dict):
        return (
            data.get("prediction"),
            data.get("confidence"),
            data.get("engine", serving_engine_for_flavor(model_flavor)),
        )
    if isinstance(data, list):
        return data, None, "deep-learning-serving"
    return data, None, serving_engine_for_flavor(model_flavor)
