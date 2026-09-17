import sys
import pytest
from unittest.mock import Mock

from src import application as runner
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = SERVICE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

@pytest.fixture
def runner_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    paths = {
        "WORKSPACE": workspace,
        "SOURCE_DIR": workspace / "source",
        "INPUT_TRAIN_DIR": workspace / "input" / "train",
        "MODEL_DIR": workspace / "model",
        "OUTPUT_DIR": workspace / "output",
    }
    for name, path in paths.items():
        monkeypatch.setattr(runner, name, path)
    for name in ("SOURCE_DIR", "INPUT_TRAIN_DIR", "MODEL_DIR", "OUTPUT_DIR"):
        paths[name].mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(runner, "log_to_mlflow", lambda **kwargs: None)
    return paths


@pytest.fixture(autouse=True)
def clean_runtime_env(monkeypatch):
    # Production configuration replaces root handlers; preserve pytest capture.
    monkeypatch.setattr(runner, "configure", Mock())
    names = (
        "S3_SOURCE_URI",
        "S3_TRAINING_DATA_URI",
        "S3_OUTPUT_URI",
        "S3_OUTPUT_UPLOAD_URL",
        "S3_OUTPUT_UPLOAD_CAPABILITY",
        "S3_REQUIREMENTS_URI",
        "ENTRY_POINT",
        "MODEL_VERSION",
        "TRAINING_JOB_ID",
        "TENANT_ID",
        "REQUIREMENTS_TEXT",
        "REDIS_URL",
        "MLFLOW_TRACKING_URI",
        "MLFLOW_EXPERIMENT_NAME",
        "MLFLOW_ARTIFACT_ROOT",
        "AWS_BUCKET_NAME",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)
