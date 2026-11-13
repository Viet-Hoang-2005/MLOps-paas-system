"""Fixtures and markers for offline static validation."""

from __future__ import annotations

import pytest

from ..utils import (
    STANDARD_APP_LABELS,
    STANDARD_GITOPS_APP_LABELS,
    STANDARD_MLOPS_LABELS,
)


@pytest.fixture(scope="session")
def expected_workload_app_labels() -> set[str]:
    return STANDARD_APP_LABELS


@pytest.fixture(scope="session")
def expected_mlops_labels() -> set[str]:
    return STANDARD_MLOPS_LABELS


@pytest.fixture(scope="session")
def expected_gitops_app_labels() -> set[str]:
    return STANDARD_GITOPS_APP_LABELS

