import io
import json
import logging
import tarfile
import zipfile
import pytest

from types import SimpleNamespace
from unittest.mock import Mock
from src import cli

class StreamResponse:
    def __init__(self, chunks=None, status_code=200, text=""):
        self.chunks = chunks or []
        self.status_code = status_code
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, chunk_size):
        return iter(self.chunks)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http")


def test_presigned_download_and_upload(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: StreamResponse([b"a", b"b"]))
    destination = tmp_path / "artifact.bin"
    cli.download_presigned_file("http://get", destination)
    assert destination.read_bytes() == b"ab"
    response = StreamResponse()
    put = Mock(return_value=response)
    monkeypatch.setattr(cli.requests, "put", put)
    cli.upload_presigned_file("http://put", destination)
    put.assert_called_once()
    with pytest.raises(ValueError):
        cli.download_presigned_file("", destination)
    with pytest.raises(ValueError):
        cli.upload_presigned_file("", destination)


def test_safe_extract_tar_and_zip(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("ok")
    archive = tmp_path / "ok.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(source, arcname="model/model.pkl")
    cli.safe_extract_tar(archive, tmp_path / "tar-out")
    assert (tmp_path / "tar-out/model/model.pkl").exists()
    bad = tmp_path / "bad.tar.gz"
    with tarfile.open(bad, "w:gz") as handle:
        info = tarfile.TarInfo("../escape")
        info.size = 1
        handle.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="unsafe"):
        cli.safe_extract_tar(bad, tmp_path / "bad-out")
    bad_zip = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad_zip, "w") as handle:
        handle.writestr("../escape", "x")
    with pytest.raises(ValueError, match="unsafe"):
        cli.safe_extract_zip(bad_zip, tmp_path / "zip-out")
    sibling_zip = tmp_path / "sibling.zip"
    with zipfile.ZipFile(sibling_zip, "w") as handle:
        handle.writestr("../zip-outside/file", "x")
    with pytest.raises(ValueError, match="unsafe"):
        cli.safe_extract_zip(sibling_zip, tmp_path / "zip-out")


def test_safe_extract_tar_rejects_links(tmp_path):
    archive = tmp_path / "link.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        info = tarfile.TarInfo("link")
        info.type = tarfile.SYMTYPE
        info.linkname = "target"
        handle.addfile(info)
    with pytest.raises(ValueError, match="links"):
        cli.safe_extract_tar(archive, tmp_path / "out")


def test_find_model_and_mapping_files(tmp_path):
    (tmp_path / "z.joblib").write_text("z")
    (tmp_path / "model.pkl").write_text("preferred")
    (tmp_path / "label_classes.json").write_text("[]")
    assert cli.find_supported_model_file(tmp_path).name == "model.pkl"
    assert cli.find_label_mapping_file(tmp_path).name == "label_classes.json"
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="no .pkl"):
        cli.find_supported_model_file(empty)


def test_webhook_headers_and_post(monkeypatch):
    monkeypatch.setenv("CONTROL_PLANE_WEBHOOK_SECRET", "secret")
    assert cli.webhook_headers() == {"X-Control-Plane-Secret": "secret"}
    post = Mock(return_value=SimpleNamespace(status_code=200, text=""))
    monkeypatch.setattr(cli.requests, "post", post)
    cli.post_webhook("http://callback", {"status": "success"})
    assert post.call_args.kwargs["headers"] == {"X-Control-Plane-Secret": "secret"}
    post.return_value = SimpleNamespace(status_code=500, text="bad")
    with pytest.raises(RuntimeError, match="HTTP 500"):
        cli.post_webhook("http://callback", {})
    post.reset_mock()
    cli.post_webhook("", {})
    post.assert_not_called()


def fake_docker_client():
    client = Mock()
    client.api.build.return_value = [{"stream": "done"}]
    client.images.push.return_value = [{"status": "pushed"}]
    return client


def test_configured_image_reference_uses_project_repository_and_build_tag(monkeypatch):
    monkeypatch.setenv("PROJECT_ID", "project-uuid")
    monkeypatch.setenv("BUILD_ID", "build-uuid")
    monkeypatch.delenv("IMAGE_REPOSITORY", raising=False)
    monkeypatch.delenv("IMAGE_TAG", raising=False)
    monkeypatch.delenv("HARBOR_REGISTRY_URL", raising=False)

    assert cli.configured_image_reference() == "image-project-uuid:build-build-uuid"


@pytest.mark.parametrize("builder,base_fragment", [
    (cli.build_custom_image, "machine-learning-serving"),
    (cli.build_bento_image, "deep-learning-serving"),
])
def test_docker_builders(monkeypatch, tmp_path, builder, base_fragment):
    client = fake_docker_client()
    monkeypatch.setattr(cli.docker, "from_env", lambda: client)
    monkeypatch.setenv("HARBOR_REGISTRY_URL", "registry.example")
    monkeypatch.setenv("HARBOR_USERNAME", "user")
    monkeypatch.setenv("HARBOR_PASSWORD", "pass")
    monkeypatch.setenv("HARBOR_USER_PROJECT", "models")
    monkeypatch.setenv("PROJECT_ID", "project-uuid")
    monkeypatch.setenv("BUILD_ID", "build-uuid")
    monkeypatch.setenv("IMAGE_REPOSITORY", "registry.example/models/image-project-uuid")
    monkeypatch.setenv("IMAGE_TAG", "build-build-uuid")
    builder(tmp_path, "VERSION", "TENANT", "numpy")
    assert base_fragment in (tmp_path / "Dockerfile").read_text()
    client.login.assert_called_once()
    client.images.push.assert_called_once()
    assert client.api.build.call_args.kwargs["tag"] == (
        "registry.example/models/image-project-uuid:build-build-uuid"
    )


def test_docker_builder_raises_build_error(monkeypatch, tmp_path):
    client = fake_docker_client()
    client.api.build.return_value = [{"errorDetail": {"message": "broken"}}]
    monkeypatch.setattr(cli.docker, "from_env", lambda: client)
    with pytest.raises(RuntimeError, match="broken"):
        cli.build_custom_image(tmp_path, "m", "t", "")


def test_parse_conda_pip_requirements(tmp_path):
    conda = tmp_path / "conda.yaml"
    conda.write_text("dependencies:\n  - python=3.10\n  - pip:\n      - numpy==1\n      - pandas\n")
    assert cli.parse_conda_pip_requirements(conda) == ["numpy==1", "pandas"]


def configure_build(monkeypatch, tmp_path, flavor="sklearn", source_type="manual_upload"):
    monkeypatch.setenv("FLAVOR", flavor)
    monkeypatch.setenv("SOURCE_TYPE", source_type)
    monkeypatch.setenv("SOURCE_DOWNLOAD_URL", "http://source")
    monkeypatch.setenv("OUTPUT_UPLOAD_URL", "http://output")
    monkeypatch.setenv("BUILD_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("TENANT_ID", "tenant")
    if source_type == "manual_upload":
        monkeypatch.setenv("SOURCE_ARTIFACT_NAME", "model.pkl")


def stub_package_helpers(monkeypatch):
    def download(url, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"artifact")

    def save(model, flavor, package_dir, requirements):
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "MLmodel").write_text("metadata")

    monkeypatch.setattr(cli, "download_presigned_file", download)
    monkeypatch.setattr(cli, "upload_presigned_file", Mock())
    monkeypatch.setattr(cli, "load_model", lambda *a: "model")
    monkeypatch.setattr(cli, "save_mlflow_model", save)


def test_read_training_summaries_from_mlops_bundle(tmp_path):
    mlops_dir = tmp_path / "nested" / "_mlops"
    mlops_dir.mkdir(parents=True)
    (mlops_dir / "metrics.json").write_text(json.dumps({"accuracy": 0.97}), encoding="utf-8")
    (mlops_dir / "params.json").write_text(json.dumps({"epochs": 10}), encoding="utf-8")
    (mlops_dir / "model_insights.json").write_text("not-json", encoding="utf-8")

    summaries, discovered = cli.read_training_summaries(tmp_path)

    assert discovered == mlops_dir
    assert summaries == {
        "metrics_summary": {"accuracy": 0.97},
        "params_summary": {"epochs": 10},
        "insights_summary": {},
    }


@pytest.mark.parametrize("flavor,base", [
    ("sklearn", "machine-learning-serving"),
    ("pytorch", "deep-learning-serving"),
])
def test_run_build_task_prepares_kaniko_context(monkeypatch, tmp_path, flavor, base):
    configure_build(monkeypatch, tmp_path, flavor)
    monkeypatch.setenv("BUILD_ENGINE", "kaniko")
    stub_package_helpers(monkeypatch)
    cli.run_build_task("version", "http://callback")
    assert base in (tmp_path / "Dockerfile").read_text()
    payload = json.loads((tmp_path / "webhook_payload.json").read_text())
    assert payload["status"] == "success" and payload["build_id"] == "version"


def test_run_build_task_docker_posts_callback(monkeypatch, tmp_path):
    configure_build(monkeypatch, tmp_path)
    monkeypatch.delenv("BUILD_ENGINE", raising=False)
    stub_package_helpers(monkeypatch)
    build = Mock()
    webhook = Mock()
    monkeypatch.setattr(cli, "build_custom_image", build)
    monkeypatch.setattr(cli, "post_webhook", webhook)
    cli.run_build_task("version", "http://callback")
    build.assert_called_once()
    assert webhook.call_args.args[1]["status"] == "success"


def test_run_build_task_validates_environment(monkeypatch):
    for name in ("FLAVOR", "SOURCE_DOWNLOAD_URL", "SOURCE_ARTIFACT_NAME", "OUTPUT_UPLOAD_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SOURCE_TYPE", "manual_upload")
    with pytest.raises(ValueError, match="Missing required"):
        cli.run_build_task("m", "callback")


def test_run_notify_task(monkeypatch, tmp_path):
    payload = {"build_id": "m", "status": "success"}
    (tmp_path / "webhook_payload.json").write_text(json.dumps(payload))
    post = Mock()
    monkeypatch.setattr(cli, "post_webhook", post)
    cli.run_notify_task(str(tmp_path), "callback")
    post.assert_called_once_with("callback", payload)
    with pytest.raises(FileNotFoundError):
        cli.run_notify_task(str(tmp_path / "missing"), "callback")


def configure_zip_task(monkeypatch, tmp_path, kaniko=False):
    monkeypatch.setenv("SOURCE_DOWNLOAD_URL", "http://source")
    monkeypatch.setenv("SOURCE_ARTIFACT_NAME", "package.zip")
    monkeypatch.setenv("BUILD_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("TENANT_ID", "tenant")
    if kaniko:
        monkeypatch.setenv("BUILD_ENGINE", "kaniko")
    else:
        monkeypatch.delenv("BUILD_ENGINE", raising=False)

    def download(url, destination):
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("model/MLmodel", "metadata")
            archive.writestr("model/requirements.txt", "numpy==1.26.4\n")

    monkeypatch.setattr(cli, "download_presigned_file", download)
    monkeypatch.setattr(cli.subprocess, "run", Mock())
    monkeypatch.setattr(cli.mlflow.pyfunc, "load_model", Mock(return_value=object()))


def test_run_test_zip_task_docker(monkeypatch, tmp_path):
    configure_zip_task(monkeypatch, tmp_path)
    build = Mock()
    webhook = Mock()
    monkeypatch.setattr(cli, "build_custom_image", build)
    monkeypatch.setattr(cli, "post_webhook", webhook)
    cli.run_test_zip_task("version", "callback")
    build.assert_called_once()
    assert webhook.call_args.args[1]["task_type"] == "TEST_ZIP"


def test_run_test_zip_task_kaniko(monkeypatch, tmp_path):
    configure_zip_task(monkeypatch, tmp_path, kaniko=True)
    cli.run_test_zip_task("version", "callback")
    payload = json.loads((tmp_path / "webhook_payload.json").read_text())
    assert payload["task_type"] == "TEST_ZIP"
    assert "machine-learning-serving" in (tmp_path / "Dockerfile").read_text()


def test_redis_log_handler(monkeypatch):
    client = Mock()
    monkeypatch.setattr(cli.redis, "from_url", lambda _: client)
    handler = cli.RedisLogHandler("redis://test", "m")
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.emit(logging.LogRecord("x", logging.INFO, "", 1, "hello", (), None))
    client.rpush.assert_called_once_with("build_logs:m", "hello")
    client.expire.assert_called_once_with("build_logs:m", 3600)


def test_main_dispatch_and_failure(monkeypatch, tmp_path):
    logger = Mock()
    monkeypatch.setattr(cli, "setup_logger", lambda _: logger)
    monkeypatch.setenv("BUILD_ID", "m")
    monkeypatch.setenv("TASK_TYPE", "NOTIFY_BUILD")
    monkeypatch.setenv("BUILD_WORKSPACE_DIR", str(tmp_path))
    run = Mock()
    monkeypatch.setattr(cli, "run_notify_task", run)
    cli.main()
    run.assert_called_once()
    monkeypatch.setattr(cli, "run_notify_task", Mock(side_effect=RuntimeError("bad")))
    webhook = Mock()
    monkeypatch.setattr(cli, "post_webhook", webhook)
    with pytest.raises(SystemExit):
        cli.main()
    assert webhook.call_args.args[1]["status"] == "error"
    assert webhook.call_args.args[1]["build_id"] == "m"
