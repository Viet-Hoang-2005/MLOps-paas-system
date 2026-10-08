"""Framework-independent interpretation of serving-worker responses."""

from typing import Any

from src.routing import serving_engine_for_flavor


def sanitize_prediction(val: Any) -> Any:
    """Normalize NumPy scalars/arrays and tensors to native Python primitives."""
    if hasattr(val, "tolist"):
        return val.tolist()
    if hasattr(val, "item"):
        return val.item()
    if isinstance(val, dict):
        return {k: sanitize_prediction(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [sanitize_prediction(v) for v in val]
    return val


def parse_worker_prediction(
    data: Any,
    model_flavor: Any,
) -> tuple[Any, float | None, str]:
    if isinstance(data, dict):
        pred = data.get("prediction")
        conf = data.get("confidence")
        engine = data.get("engine", serving_engine_for_flavor(model_flavor))
    elif isinstance(data, list):
        pred, conf, engine = data, None, "deep-learning-serving"
    else:
        pred, conf, engine = data, None, serving_engine_for_flavor(model_flavor)

    pred = sanitize_prediction(pred)

    if hasattr(conf, "item"):
        conf = conf.item()
    if conf is not None:
        try:
            conf = float(conf)
        except (ValueError, TypeError):
            conf = None

    return pred, conf, engine
