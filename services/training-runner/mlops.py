"""Small, framework-independent helpers for a training workspace.

The runner sets the three MLOPS_* paths for workspace-based runs.  This module
does not download inputs, validate uploaded models, or mark a run successful;
those operations remain the runner's responsibility.
"""

import json
import os
import shutil
from pathlib import Path


def _directory(name):
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"{name} is not configured for this training run")
    path = Path(value)
    if not path.is_dir() or path.is_symlink():
        raise RuntimeError(f"{name} is not an available directory")
    return path.resolve(strict=True)


def _inside(root, path):
    try:
        return path.is_relative_to(root)
    except AttributeError:  # Python 3.8 compatibility for user environments
        return path == root or root in path.parents


def input_path(relative_path):
    """Resolve an existing path within the read-only training input."""
    root = _directory("MLOPS_INPUT_DIR")
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Input path must be relative to the input directory")
    path = (root / relative).resolve(strict=True)
    if not _inside(root, path):
        raise ValueError("Input path must stay within the input directory")
    return path


def work_dir():
    """Return the run's writable temporary working directory."""
    return _directory("MLOPS_WORK_DIR")


def export_model(path):
    """Copy one model file or directory from the working directory for upload."""
    work = work_dir()
    output = _directory("MLOPS_EXPORT_DIR")
    if _inside(work, output) or _inside(output, work):
        raise RuntimeError("Model staging must be separate from the working directory")
    source = Path(path)
    source = source if source.is_absolute() else work / source
    if source.is_symlink():
        raise ValueError("A model cannot be a symbolic link")
    source = source.resolve(strict=True)
    if source == work or not _inside(work, source) or not (source.is_file() or source.is_dir()):
        raise ValueError("Model must be a file or directory inside the working directory")
    if source.is_dir():
        for item in source.rglob("*"):
            if item.is_symlink() or not (item.is_file() or item.is_dir()):
                raise ValueError("Model directories cannot contain symbolic links or special files")
    manifest = output / "export.json"
    target = output / "model"
    if manifest.exists() or target.exists():
        raise RuntimeError("Only one model may be exported per training run")
    try:
        if source.is_dir():
            shutil.copytree(source, target, symlinks=False)
        else:
            target.mkdir()
            shutil.copy2(source, target / source.name)
        if not any(item.is_file() for item in target.rglob("*")):
            raise ValueError("The exported model directory is empty")
        manifest.write_text(json.dumps({"model": "model"}), encoding="utf-8")
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return target
