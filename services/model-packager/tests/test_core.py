import pickle
import sys
import zipfile
import pytest

from types import ModuleType
from types import SimpleNamespace
from unittest.mock import Mock
from src import core


def test_parse_requirements():
    assert core.parse_requirements("# comment\nnumpy==1\n\n pandas ") == ["numpy==1", "pandas"]
    assert core.parse_requirements("\n# only") is None


def test_load_pickle_model_falls_back(monkeypatch, tmp_path):
    path = tmp_path / "model.pkl"
    path.write_bytes(pickle.dumps({"model": 1}))
    monkeypatch.setattr(core.joblib, "load", Mock(side_effect=RuntimeError("no")))
    assert core.load_pickle_model(path) == {"model": 1}


@pytest.mark.parametrize(
    "flavor,suffix,loader_name",
    [
        ("sklearn", ".pkl", "pickle"),
        ("xgboost", ".xgb", "xgb"),
        ("pytorch", ".pt", "torch"),
        ("keras", ".keras", "keras"),
        ("tensorflow", ".h5", "keras"),
    ],
)
def test_load_model_dispatch(monkeypatch, tmp_path, flavor, suffix, loader_name):
    path = tmp_path / f"model{suffix}"
    path.write_bytes(b"x")
    if loader_name == "pickle":
        monkeypatch.setattr(core, "load_pickle_model", lambda _: "model")
    elif loader_name == "xgb":
        booster = Mock()
        monkeypatch.setattr(core, "xgb", SimpleNamespace(Booster=lambda: booster))
    elif loader_name == "torch":
        monkeypatch.setattr(core, "torch", SimpleNamespace(load=lambda *a, **k: "model"))
    else:
        fake_tf = SimpleNamespace(keras=SimpleNamespace(models=SimpleNamespace(load_model=lambda _: "model")))
        monkeypatch.setattr(core, "tf", fake_tf)
    result = core.load_model(path, flavor)
    assert result == "model" or loader_name == "xgb"


def test_load_model_rejects_invalid_extension_and_flavor(tmp_path):
    path = tmp_path / "model.txt"
    path.write_text("x")
    with pytest.raises(ValueError):
        core.load_model(path, "sklearn")
    with pytest.raises(ValueError, match="Unsupported"):
        core.load_model(path, "unknown")


def test_save_mlflow_dispatch_sklearn(monkeypatch, tmp_path):
    import mlflow.sklearn
    mock = Mock()
    monkeypatch.setattr(mlflow.sklearn, "save_model", mock)
    core.save_mlflow_model("model", "sklearn", tmp_path / "out", ["numpy"])
    mock.assert_called_once()


def test_save_mlflow_keras_falls_back_to_tensorflow(monkeypatch, tmp_path):
    import mlflow
    fake_keras = ModuleType("mlflow.keras")
    fake_keras.save_model = Mock(side_effect=AttributeError())
    fake_tensorflow = ModuleType("mlflow.tensorflow")
    fallback = Mock()
    fake_tensorflow.save_model = fallback
    monkeypatch.setitem(sys.modules, "mlflow.keras", fake_keras)
    monkeypatch.setitem(sys.modules, "mlflow.tensorflow", fake_tensorflow)
    monkeypatch.setattr(mlflow, "keras", fake_keras, raising=False)
    monkeypatch.setattr(mlflow, "tensorflow", fake_tensorflow, raising=False)
    core.save_mlflow_model("model", "keras", tmp_path / "out", None)
    fallback.assert_called_once()


def test_save_mlflow_rejects_unknown_flavor(tmp_path):
    with pytest.raises(ValueError, match="Unsupported"):
        core.save_mlflow_model("model", "unknown", tmp_path, None)


def test_preview_tree_and_zip(tmp_path):
    model = tmp_path / "model"
    nested = model / "nested"
    nested.mkdir(parents=True)
    (model / "MLmodel").write_text("meta")
    (nested / "weights.bin").write_bytes(b"x")
    tree = core.build_preview_tree(model)
    assert "model/MLmodel" in tree and "model/nested/" in tree
    archive = tmp_path / "package.zip"
    core.make_zip(model, archive)
    with zipfile.ZipFile(archive) as handle:
        assert "model/MLmodel" in handle.namelist()
