from unittest.mock import Mock

import pytest

from src import application as main


@pytest.fixture(autouse=True)
def isolated_logging(monkeypatch):
    monkeypatch.setattr(main, "configure", Mock())
    monkeypatch.setattr(main, "REDIS_URL", "")
    # setup_logger creates a runtime adapter; restore it after each test.
    monkeypatch.setattr(main, "runtime_log", main.RuntimeLog(main.logger))
