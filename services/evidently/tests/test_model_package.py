import hashlib
import io
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from src import application as main
from src import data


def _make_zip(files: dict[str, bytes], symlinks: dict[str, str] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
        if symlinks:
            for name, target in symlinks.items():
                info = zipfile.ZipInfo(name)
                # Unix symlink attribute: 0o120000 | permissions
                info.external_attr = 0o120777 << 16
                zf.writestr(info, target.encode("utf-8"))
    return buffer.getvalue()


class FakeStreamingResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=1024):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i : i + chunk_size]


def test_download_model_metadata_success(tmp_path):
    mlmodel_bytes = b"flavor: sklearn\nsignature:\n  inputs: '[{\"name\": \"f1\", \"type\": \"double\"}]'\n"
    zip_bytes = _make_zip({"model/MLmodel": mlmodel_bytes})
    sha = hashlib.sha256(zip_bytes).hexdigest()

    fake_requests = Mock()
    info_resp = Mock(status_code=200)
    info_resp.json.return_value = {
        "url": "https://s3.amazonaws.com/test-bucket/model-package.zip?AWSAccessKeyId=SECRET",
        "size_bytes": len(zip_bytes),
        "checksum": f"sha256:{sha}",
    }
    fake_requests.get.side_effect = [
        info_resp,
        FakeStreamingResponse(zip_bytes, status_code=200),
    ]

    result = data.download_model_metadata(
        webhook_url="http://cp:8000/internal/webhooks/drift-runs/11111111-1111-1111-1111-111111111111/",
        secret="secret",
        run_id="11111111-1111-1111-1111-111111111111",
        tenant_id="T-123",
        project_id="22222222-2222-2222-2222-222222222222",
        version_id="33333333-3333-3333-3333-333333333333",
        temp_root=tmp_path,
        requests_module=fake_requests,
    )

    assert result is not None
    cache_path = Path(result)
    assert cache_path.exists()
    assert (cache_path / "MLmodel").read_bytes() == mlmodel_bytes


def test_download_model_metadata_retries_on_s3_403(tmp_path):
    mlmodel_bytes = b"flavor: sklearn\n"
    zip_bytes = _make_zip({"MLmodel": mlmodel_bytes})
    sha = hashlib.sha256(zip_bytes).hexdigest()

    fake_requests = Mock()
    info_resp1 = Mock(status_code=200)
    info_resp1.json.return_value = {"url": "https://s3/expired", "size_bytes": len(zip_bytes), "checksum": sha}
    info_resp2 = Mock(status_code=200)
    info_resp2.json.return_value = {"url": "https://s3/fresh", "size_bytes": len(zip_bytes), "checksum": sha}

    fake_requests.get.side_effect = [
        info_resp1,
        FakeStreamingResponse(b"", status_code=403),
        info_resp2,
        FakeStreamingResponse(zip_bytes, status_code=200),
    ]

    result = data.download_model_metadata(
        webhook_url="http://cp:8000/internal/webhooks/drift-runs/run1/",
        secret="secret",
        run_id="run1",
        tenant_id="T-123",
        project_id="p1",
        version_id="v1",
        temp_root=tmp_path,
        requests_module=fake_requests,
    )

    assert result is not None
    assert (Path(result) / "MLmodel").read_bytes() == mlmodel_bytes
    assert fake_requests.get.call_count == 4


def test_download_model_metadata_returns_none_on_404_no_package(tmp_path):
    fake_requests = Mock()
    info_resp = Mock(status_code=404)
    fake_requests.get.return_value = info_resp

    result = data.download_model_metadata(
        webhook_url="http://cp:8000/internal/webhooks/drift-runs/run1/",
        secret="secret",
        run_id="run1",
        tenant_id="T-123",
        project_id="p1",
        version_id="v1",
        temp_root=tmp_path,
        requests_module=fake_requests,
    )

    assert result is None


def test_download_model_metadata_rejects_oversized_declared_package(tmp_path):
    fake_requests = Mock()
    info_resp = Mock(status_code=200)
    info_resp.json.return_value = {"url": "https://s3/pkg", "size_bytes": 2 * 1024**3}
    fake_requests.get.return_value = info_resp

    with pytest.raises(ValueError, match="exceeds the allowed size"):
        data.download_model_metadata(
            webhook_url="http://cp:8000/internal/webhooks/drift-runs/run1/",
            secret="secret",
            run_id="run1",
            tenant_id="T-123",
            project_id="p1",
            version_id="v1",
            temp_root=tmp_path,
            requests_module=fake_requests,
        )


def test_download_model_metadata_rejects_checksum_mismatch(tmp_path):
    zip_bytes = _make_zip({"MLmodel": b"data"})
    fake_requests = Mock()
    info_resp = Mock(status_code=200)
    info_resp.json.return_value = {
        "url": "https://s3/pkg",
        "size_bytes": len(zip_bytes),
        "checksum": "0000000000000000000000000000000000000000000000000000000000000000",
    }
    fake_requests.get.side_effect = [
        info_resp,
        FakeStreamingResponse(zip_bytes, status_code=200),
    ]

    with pytest.raises(ValueError, match="checksum mismatch"):
        data.download_model_metadata(
            webhook_url="http://cp:8000/internal/webhooks/drift-runs/run1/",
            secret="secret",
            run_id="run1",
            tenant_id="T-123",
            project_id="p1",
            version_id="v1",
            temp_root=tmp_path,
            requests_module=fake_requests,
        )


def test_download_model_metadata_rejects_symlinks(tmp_path):
    zip_bytes = _make_zip({"real": b"content"}, symlinks={"MLmodel": "real"})
    sha = hashlib.sha256(zip_bytes).hexdigest()

    fake_requests = Mock()
    info_resp = Mock(status_code=200)
    info_resp.json.return_value = {"url": "https://s3/pkg", "size_bytes": len(zip_bytes), "checksum": sha}
    fake_requests.get.side_effect = [
        info_resp,
        FakeStreamingResponse(zip_bytes, status_code=200),
    ]

    with pytest.raises(ValueError, match="Unsafe model package"):
        data.download_model_metadata(
            webhook_url="http://cp:8000/internal/webhooks/drift-runs/run1/",
            secret="secret",
            run_id="run1",
            tenant_id="T-123",
            project_id="p1",
            version_id="v1",
            temp_root=tmp_path,
            requests_module=fake_requests,
        )


def test_download_model_metadata_rejects_multiple_mlmodels(tmp_path):
    zip_bytes = _make_zip({"m1/MLmodel": b"1", "m2/MLmodel": b"2"})
    sha = hashlib.sha256(zip_bytes).hexdigest()

    fake_requests = Mock()
    info_resp = Mock(status_code=200)
    info_resp.json.return_value = {"url": "https://s3/pkg", "size_bytes": len(zip_bytes), "checksum": sha}
    fake_requests.get.side_effect = [
        info_resp,
        FakeStreamingResponse(zip_bytes, status_code=200),
    ]

    with pytest.raises(ValueError, match="ambiguous"):
        data.download_model_metadata(
            webhook_url="http://cp:8000/internal/webhooks/drift-runs/run1/",
            secret="secret",
            run_id="run1",
            tenant_id="T-123",
            project_id="p1",
            version_id="v1",
            temp_root=tmp_path,
            requests_module=fake_requests,
        )


def test_download_model_metadata_rejects_oversized_mlmodel(tmp_path):
    zip_bytes = _make_zip({"MLmodel": b"x" * (1024 * 1024 + 1)})
    sha = hashlib.sha256(zip_bytes).hexdigest()

    fake_requests = Mock()
    info_resp = Mock(status_code=200)
    info_resp.json.return_value = {"url": "https://s3/pkg", "size_bytes": len(zip_bytes), "checksum": sha}
    fake_requests.get.side_effect = [
        info_resp,
        FakeStreamingResponse(zip_bytes, status_code=200),
    ]

    with pytest.raises(ValueError, match="unavailable or ambiguous"):
        data.download_model_metadata(
            webhook_url="http://cp:8000/internal/webhooks/drift-runs/run1/",
            secret="secret",
            run_id="run1",
            tenant_id="T-123",
            project_id="p1",
            version_id="v1",
            temp_root=tmp_path,
            requests_module=fake_requests,
        )


def test_get_data_definition_falls_back_cleanly_on_package_error(monkeypatch):
    monkeypatch.setattr(main, "resolve_model_dir", Mock(side_effect=ValueError("DownloadFailed")))
    reference = pd.DataFrame({"feat_num": [1.0, 2.0], "feat_cat": ["a", "b"], "prediction": [0, 1]})

    defn = main.get_data_definition(reference)
    assert "feat_num" in defn.numerical_columns
    assert "feat_cat" in defn.categorical_columns


def test_get_data_definition_cleans_up_temp_dir(monkeypatch, tmp_path):
    model_dir = tmp_path / "model_cache"
    model_dir.mkdir()
    (model_dir / "MLmodel").write_text("flavor: sklearn")

    signature = SimpleNamespace(
        inputs=[SimpleNamespace(name="feature_1", type="double")]
    )
    monkeypatch.setattr(main, "resolve_model_dir", lambda *a: str(model_dir))
    monkeypatch.setattr(main.mlflow.models, "get_model_info", lambda _: SimpleNamespace(signature=signature))

    reference = pd.DataFrame({"feature_1": [1.0]})
    defn = main.get_data_definition(reference)

    assert defn.numerical_columns == ["feature_1"]
    # Verify temp dir was cleaned up in finally block
    assert not model_dir.exists()


def test_log_hygiene_does_not_contain_presigned_url_or_secret(monkeypatch):
    from src.logging_utils import sanitize

    secret = "my-super-secret-key-12345"
    presigned_url = "https://my-bucket.s3.amazonaws.com/model-package.zip?AWSAccessKeyId=AKIAIOSFODNN7EXAMPLE&Signature=vjbyPxybdZaNmGa%2ByT272YEAiv4%3D"
    raw_message = f"Failed to download package from {presigned_url} with secret {secret}"

    monkeypatch.setenv("CONTROL_PLANE_WEBHOOK_SECRET", secret)
    sanitized = sanitize(raw_message)

    assert secret not in sanitized
    assert "AWSAccessKeyId" not in sanitized
    assert "Signature" not in sanitized
    assert "[REDACTED" in sanitized


def test_no_botocore_dependency():
    import sys
    # Verify that evidently package flow does not require or load boto3/botocore
    assert "boto3" not in sys.modules
    assert "botocore" not in sys.modules
