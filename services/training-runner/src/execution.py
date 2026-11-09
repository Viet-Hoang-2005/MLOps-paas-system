"""Training subprocess protocol and model archive helpers."""

import json
import os
import stat
import tarfile


MAX_MODEL_FILES = 100_000
MAX_MODEL_BYTES = 20 * 1024 * 1024 * 1024


def is_metric_protocol_line(message: str) -> bool:
    if "\n" in message or "\r" in message or len(message) > 16384:
        return False
    stripped = message.lstrip()
    for prefix in ("METRIC_JSON:", "METRIC_JSON "):
        if stripped.startswith(prefix):
            try:
                return isinstance(json.loads(stripped[len(prefix) :]), dict)
            except (ValueError, RecursionError):
                return False
    return False


def validate_model_tree(model_dir):
    # User code controls this directory. Do not follow links or allow special
    # files into the archive, including under the generated metadata directory.
    files = []
    total_bytes = 0
    if not stat.S_ISDIR(os.stat(model_dir, follow_symlinks=False).st_mode):
        raise RuntimeError("Model output root must be a real directory.")
    pending = [model_dir]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                info = os.stat(entry.path, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    pending.append(entry.path)
                elif stat.S_ISREG(info.st_mode) and info.st_nlink <= 1:
                    total_bytes += info.st_size
                    files.append((entry.path, info))
                    if len(files) > MAX_MODEL_FILES or total_bytes > MAX_MODEL_BYTES:
                        raise RuntimeError("Model output exceeds the allowed file count or size.")
                else:
                    raise RuntimeError("Model output contains a link or unsupported file type.")

    return files


def create_model_archive(archive_path, model_dir, metadata_dir_name, log):
    files = validate_model_tree(model_dir)
    if not any(metadata_dir_name not in os.path.relpath(path, model_dir).split(os.sep) for path, _ in files):
        raise RuntimeError("Training completed but SM_MODEL_DIR does not contain any model files.")
    log(f"Packaging {len(files)} model file(s) into model.tar.gz")
    try:
        with tarfile.open(archive_path, "w:gz") as archive:
            for path, expected in files:
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
                fd = os.open(path, flags)
                with os.fdopen(fd, "rb") as source:
                    actual = os.fstat(source.fileno())
                    if (not stat.S_ISREG(actual.st_mode) or actual.st_nlink > 1 or
                            (actual.st_dev, actual.st_ino, actual.st_size) !=
                            (expected.st_dev, expected.st_ino, expected.st_size)):
                        raise RuntimeError("Model output changed while it was being packaged.")
                    name = os.path.relpath(path, model_dir).replace(os.sep, "/")
                    info = tarfile.TarInfo(name=name)
                    info.size = actual.st_size
                    info.mode = 0o644
                    info.mtime = int(actual.st_mtime)
                    archive.addfile(info, source)
    except Exception:
        try:
            os.unlink(archive_path)
        except FileNotFoundError:
            pass
        raise
