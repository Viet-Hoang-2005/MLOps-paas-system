import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src import notify


def test_callback_preserves_payload_auth_and_idempotency(monkeypatch, tmp_path):
    (tmp_path / "webhook_payload.json").write_text('{"build_id":"example","value":NaN}', encoding="utf-8")
    (tmp_path / "image-digest").write_text("sha256:example", encoding="utf-8")
    for key, value in {
        "BUILD_ID": "example", "BUILD_WORKSPACE_DIR": str(tmp_path), "IMAGE_URI": "registry/image:tag",
        "CONTROL_PLANE_WEBHOOK_URL": "https://callback.invalid", "CONTROL_PLANE_WEBHOOK_SECRET": "secret",
    }.items():
        monkeypatch.setenv(key, value)
    post = Mock(return_value=SimpleNamespace(status_code=200))
    monkeypatch.setattr(notify.requests, "post", post)
    notify.main()
    sent = post.call_args.kwargs
    assert sent["json"] == {"build_id": "example", "value": None, "image_uri": "registry/image:tag", "image_digest": "sha256:example"}
    assert sent["headers"]["X-Control-Plane-Secret"] == "secret"
    assert sent["headers"]["Idempotency-Key"].startswith("build-example-")
    assert sent["allow_redirects"] is False


def test_entrypoint_does_not_import_ml_frameworks():
    code = "import runpy,sys; runpy.run_module('src.main',run_name='__main__'); print('ML_IMPORTS', any(x in sys.modules for x in ('torch','tensorflow','mlflow','src.core')))"
    env = {**os.environ, "TASK_TYPE": "NOTIFY_BUILD", "BUILD_ID": ""}
    # Missing BUILD_ID exits before networking; inspect loaded modules in a finally block.
    code = "try:\n " + code + "\nexcept SystemExit:\n print('ML_IMPORTS', any(x in sys.modules for x in ('torch','tensorflow','mlflow','src.core')))"
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    assert "ML_IMPORTS False" in result.stdout


def test_missing_payload_fails_without_leaking_secret(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BUILD_ID", "example")
    monkeypatch.setenv("BUILD_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("CONTROL_PLANE_WEBHOOK_SECRET", "private-secret")
    with pytest.raises(SystemExit, match="1"):
        notify.main()
    captured = capsys.readouterr()
    assert "private-secret" not in captured.out + captured.err
