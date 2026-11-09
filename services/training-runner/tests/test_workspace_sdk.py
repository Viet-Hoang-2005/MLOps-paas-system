import json

import pytest

import mlops


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    roots = {name: tmp_path / name for name in ("input", "work", "export")}
    for name, path in roots.items():
        path.mkdir()
        monkeypatch.setenv(f"MLOPS_{name.upper()}_DIR", str(path))
    return roots


def test_resolves_inputs_and_rejects_escape(workspace, tmp_path):
    data = workspace["input"] / "data.csv"
    data.write_text("x\n1\n", encoding="utf-8")
    assert mlops.input_path("data.csv") == data
    assert mlops.work_dir() == workspace["work"]
    with pytest.raises(ValueError):
        mlops.input_path("../work")
    with pytest.raises(ValueError):
        mlops.input_path(tmp_path)


def test_exports_a_copy_once(workspace):
    model = workspace["work"] / "model.pkl"
    model.write_bytes(b"model")
    target = mlops.export_model("model.pkl")
    model.write_bytes(b"changed")
    assert (target / "model.pkl").read_bytes() == b"model"
    assert json.loads((workspace["export"] / "export.json").read_text()) == {"model": "model"}
    with pytest.raises(RuntimeError, match="Only one"):
        mlops.export_model(model)


def test_rejects_empty_models_and_paths_outside_workspace(workspace):
    empty = workspace["work"] / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="empty"):
        mlops.export_model(empty)
    assert not (workspace["export"] / "model").exists()
    with pytest.raises(ValueError, match="inside"):
        mlops.export_model(workspace["input"])
