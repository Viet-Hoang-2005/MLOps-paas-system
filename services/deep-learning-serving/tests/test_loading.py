import pytest
from src import loading

def test_download_model_artifact_local_directory(tmp_path):
    assert loading.download_model_artifact("m", str(tmp_path)) == tmp_path


def test_download_model_artifact_missing(tmp_path):
    with pytest.raises(RuntimeError, match="DL model artifact"):
        loading.download_model_artifact("m", str(tmp_path / "missing"))


def test_resolve_mlflow_model_dir(tmp_path):
    (tmp_path / "MLmodel").write_text("x")
    assert loading.resolve_mlflow_model_dir(tmp_path) == tmp_path
    (tmp_path / "MLmodel").unlink()
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "MLmodel").write_text("x")
    assert loading.resolve_mlflow_model_dir(tmp_path) == nested
    (nested / "MLmodel").unlink()
    with pytest.raises(FileNotFoundError):
        loading.resolve_mlflow_model_dir(tmp_path)
