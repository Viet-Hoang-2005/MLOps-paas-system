import sys
from types import ModuleType
from unittest.mock import Mock

import pytest
import mlflow

# These tests exercise packaging/dispatch, not ML framework initialization.
# Keep optional native runtimes out of this isolated service test process.
_framework_patches = pytest.MonkeyPatch()
for name in ("torch", "tensorflow", "keras", "xgboost"):
    _framework_patches.setitem(sys.modules, name, ModuleType(name))
for flavor in ("pytorch", "tensorflow", "keras", "xgboost"):
    module = ModuleType(f"mlflow.{flavor}")
    module.save_model = Mock()
    _framework_patches.setitem(sys.modules, module.__name__, module)
    _framework_patches.setattr(mlflow, flavor, module, raising=False)

from src import tasks as cli


@pytest.fixture(autouse=True)
def isolated_logging_and_docker(monkeypatch):
    monkeypatch.setattr(cli, "configure", Mock())
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setattr(cli.docker, "from_env", Mock())


def pytest_unconfigure(config):
    _framework_patches.undo()
