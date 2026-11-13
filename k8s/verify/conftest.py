"""Session-level pytest fixtures for K8s verification suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from .utils import ValidationContext, prepared_context, repository_root


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return repository_root()


@pytest.fixture(scope="session")
def k8s_dir(repo_root: Path) -> Path:
    return repo_root / "k8s"


@pytest.fixture(scope="session")
def all_k8s_yaml_files(k8s_dir: Path) -> list[Path]:
    files: list[Path] = []
    for ext in ("*.yaml", "*.yml"):
        for path in k8s_dir.rglob(ext):
            # Ignore hidden dirs or pycache
            if any(part.startswith((".", "__")) for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


@pytest.fixture(scope="session")
def context(repo_root: Path) -> ValidationContext:
    with prepared_context(repo_root) as ctx:
        yield ctx

