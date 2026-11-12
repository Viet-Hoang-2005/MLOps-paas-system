"""Versioned, non-executing validation and packaging of training outputs."""

import hashlib
import io
import json
import os
import stat
import tarfile
from pathlib import Path

VERSION = 2
MODEL_EXTENSIONS = {
    "sklearn": {".pkl", ".joblib"},
    "xgboost": {".pkl", ".joblib"},
    "pytorch": {".pt", ".pth"},
    "tensorflow": {".h5", ".keras"},
    "keras": {".h5", ".keras"},
}
METADATA_EXTENSIONS = {".json", ".csv", ".txt", ".md", ".png", ".jpg", ".jpeg", ".pdf"}
MAX_FILES = 20_000
MAX_MODEL_BYTES = 20 * 1024**3
MAX_METADATA_BYTES = 512 * 1024**2
MAX_METADATA_FILE = 100 * 1024**2


def safe_name(name):
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        raise ValueError("Invalid output path.")
    if any(part in {"", ".", "..", "_mlops"} or ":" in part for part in name.split("/")):
        raise ValueError("Reserved or unsafe output path.")
    return name


def collect(root, group, flavor):
    root = Path(root)
    if not stat.S_ISDIR(root.lstat().st_mode):
        raise ValueError("Output root must be a real directory.")
    allowed = MODEL_EXTENSIONS.get(flavor) if group == "model" else METADATA_EXTENSIONS
    if not allowed:
        raise ValueError("Unsupported training framework.")
    result, total = [], 0
    for directory, folders, filenames in os.walk(root, followlinks=False):
        for filename in folders + filenames:
            path = Path(directory) / filename
            relative = safe_name(path.relative_to(root).as_posix())
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("Output contains a link or special file.")
            if path.suffix.lower() not in allowed:
                raise ValueError(f"Unsupported {group} file: {relative}. Write metadata to SM_OUTPUT_DIR.")
            if group == "model" and info.st_size == 0:
                raise ValueError("Model files must not be empty.")
            if group == "model" and info.st_size == 0:
                raise ValueError("Model files must not be empty.")
            total += info.st_size
            if group == "metadata" and info.st_size > MAX_METADATA_FILE:
                raise ValueError("Metadata file exceeds 100 MiB.")
            if total > (MAX_MODEL_BYTES if group == "model" else MAX_METADATA_BYTES):
                raise ValueError("Output group exceeds its size limit.")
            result.append((path, info, f"{group}/{relative}"))
            if len(result) > MAX_FILES:
                raise ValueError("Too many output files.")
    if group == "model" and not result:
        raise ValueError("SM_MODEL_DIR must contain at least one model.")
    return sorted(result, key=lambda entry: entry[2])


def package(destination, model_dir, metadata_dir, system_dir, flavor):
    files = collect(model_dir, "model", flavor) + collect(metadata_dir, "metadata", flavor)
    if len(files) > MAX_FILES:
        raise ValueError("Too many output files.")
    manifest = {"version": VERSION, "framework": flavor, "files": []}
    destination = Path(destination)
    for root in (model_dir, metadata_dir, system_dir):
        if destination.resolve().is_relative_to(Path(root).resolve()):
            raise ValueError("Archive must be outside output source directories.")
    try:
        with tarfile.open(destination, "w:gz") as archive:
            for path, expected, name in files:
                digest = hashlib.sha256()
                fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
                with os.fdopen(fd, "rb") as source:
                    actual = os.fstat(source.fileno())
                    if (actual.st_dev, actual.st_ino, actual.st_size, actual.st_mtime_ns) != (
                        expected.st_dev,
                        expected.st_ino,
                        expected.st_size,
                        expected.st_mtime_ns,
                    ) or actual.st_nlink != 1:
                        raise ValueError("Output changed during packaging.")
                    # Hash and copy from the same open descriptor, then verify stability.
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
                    source.seek(0)
                    info = tarfile.TarInfo(name)
                    info.size, info.mode = actual.st_size, 0o644
                    archive.addfile(info, source)
                    after = os.fstat(source.fileno())
                    if (after.st_size, after.st_mtime_ns) != (actual.st_size, actual.st_mtime_ns):
                        raise ValueError("Output changed during packaging.")
                manifest["files"].append(
                    {
                        "path": name,
                        "group": name.split("/")[0],
                        "size_bytes": actual.st_size,
                        "checksum": digest.hexdigest(),
                    }
                )
            for path in sorted(Path(system_dir).glob("*")):
                if path.is_file() and not path.is_symlink():
                    archive.add(path, arcname="_mlops/" + path.name, recursive=False)
            raw = json.dumps(manifest, allow_nan=False).encode()
            info = tarfile.TarInfo("_mlops/output_manifest.json")
            info.size, info.mode = len(raw), 0o644
            archive.addfile(info, io.BytesIO(raw))
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return manifest
