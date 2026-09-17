"""Training subprocess protocol and model archive helpers."""

import json
import tarfile


def is_metric_protocol_line(message: str) -> bool:
    if "\n" in message or "\r" in message or len(message) > 16384:
        return False
    stripped = message.lstrip()
    for prefix in ("METRIC_JSON:", "METRIC_JSON "):
        if stripped.startswith(prefix):
            try:
                return isinstance(json.loads(stripped[len(prefix):]), dict)
            except (ValueError, RecursionError):
                return False
    return False


def create_model_archive(archive_path, model_dir, metadata_dir_name, log):
    model_files = [
        item for item in model_dir.rglob("*")
        if item.is_file() and metadata_dir_name not in item.relative_to(model_dir).parts
    ]
    if not model_files:
        raise RuntimeError("Training completed but SM_MODEL_DIR does not contain any model files.")
    log(f"Packaging {len(model_files)} model file(s) into model.tar.gz")
    with tarfile.open(archive_path, "w:gz") as archive:
        for item in model_dir.rglob("*"):
            if item.is_file():
                archive.add(item, arcname=item.relative_to(model_dir))
