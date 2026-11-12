import json
import os
import tarfile

import pytest

from src.output_contract import collect, package


@pytest.fixture
def output_dirs(tmp_path):
    model, metadata, system = (tmp_path / name for name in ("models", "metadata", "system"))
    for folder in (model, metadata, system):
        folder.mkdir()
    (model / "first.joblib").write_bytes(b"first-model")
    (model / "second.joblib").write_bytes(b"second-model")
    (metadata / "arbitrary-name.json").write_text('{"accuracy":0.9}')
    (system / "stdout.txt").write_text("training log")
    return model, metadata, system


def test_package_preserves_groups_and_original_metadata(tmp_path, output_dirs):
    model, metadata, system = output_dirs
    archive = tmp_path / "result.tar.gz"
    manifest = package(archive, model, metadata, system, "xgboost")
    assert manifest["version"] == 2 and len(manifest["files"]) == 3
    with tarfile.open(archive) as result:
        assert set(result.getnames()) == {
            "model/first.joblib",
            "model/second.joblib",
            "metadata/arbitrary-name.json",
            "_mlops/stdout.txt",
            "_mlops/output_manifest.json",
        }
        assert json.load(result.extractfile("_mlops/output_manifest.json")) == manifest
        assert result.extractfile("metadata/arbitrary-name.json").read() == b'{"accuracy":0.9}'


@pytest.mark.parametrize("filename", ["metrics.json", "model.xgb", "model.py", "model.pt"])
def test_rejects_non_model_or_wrong_framework(output_dirs, filename):
    model, _, _ = output_dirs
    (model / filename).write_bytes(b"invalid")
    with pytest.raises(ValueError):
        collect(model, "model", "xgboost")


def test_missing_model_and_reserved_namespace(output_dirs):
    model, metadata, _ = output_dirs
    for item in model.iterdir():
        item.unlink()
    with pytest.raises(ValueError, match="at least one"):
        collect(model, "model", "xgboost")
    (metadata / "_mlops").mkdir()
    with pytest.raises(ValueError, match="Reserved"):
        collect(metadata, "metadata", "xgboost")


def test_symlink_and_hardlink_are_rejected(output_dirs):
    model, metadata, _ = output_dirs
    try:
        os.link(model / "first.joblib", metadata / "link.json")
    except OSError:
        pytest.skip("Hard links unavailable on this filesystem")
    with pytest.raises(ValueError, match="link"):
        collect(model, "model", "xgboost")


def test_reports_and_metadata_size_limits(output_dirs, monkeypatch):
    import src.output_contract as contract

    _, metadata, _ = output_dirs
    (metadata / "report.pdf").write_bytes(b"%PDF")
    assert len(collect(metadata, "metadata", "xgboost")) == 2
    monkeypatch.setattr(contract, "MAX_METADATA_FILE", 1)
    with pytest.raises(ValueError):
        collect(metadata, "metadata", "xgboost")


def test_archive_cannot_be_created_in_user_outputs(output_dirs):
    model, metadata, system = output_dirs
    with pytest.raises(ValueError, match="outside"):
        package(metadata / "model.tar.gz", model, metadata, system, "xgboost")
