"""Tabular serving contracts at the MLflow input boundary."""

import numpy as np
import pytest
from src.inference import run_inference


class StrictDoubleModel:
    def predict(self, frame):
        assert list(frame.columns) == ["Destination Port", "label"]
        assert frame["Destination Port"].dtype == np.dtype("float64")
        assert frame.at[0, "Destination Port"] == 53.0
        assert frame.at[0, "label"] == "BENIGN"
        return np.array([0])


def test_integer_json_number_matches_double_signature():
    loaded = {
        "model": StrictDoubleModel(),
        "expected_features": ["Destination Port", "label"],
        "float64_features": ["Destination Port"],
    }
    prediction, confidence = run_inference(loaded, {"label": "BENIGN", "Destination Port": 53})
    assert prediction == 0
    assert confidence is None


@pytest.mark.parametrize("value", [True, "53", float("nan"), float("inf")])
def test_double_signature_rejects_non_numeric_or_nonfinite(value):
    loaded = {
        "model": StrictDoubleModel(),
        "expected_features": ["Destination Port", "label"],
        "float64_features": ["Destination Port"],
    }
    with pytest.raises(ValueError, match="finite number"):
        run_inference(loaded, {"label": "BENIGN", "Destination Port": value})
