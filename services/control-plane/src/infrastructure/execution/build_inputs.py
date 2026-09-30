"""Resolve optional, build-scoped inputs for a model packaging attempt."""

from pathlib import Path


def label_mapping_input(build, storage):
    """Return a presigned GET URL and basename, or empty values when absent."""
    asset = build.input_assets.filter(kind="label_mapping").exclude(s3_uri="").first()
    if asset is not None:
        uri = asset.s3_uri
    elif build.version_id:
        asset = build.version.artifacts.filter(kind="label_mapping").exclude(uri="").first()
        uri = asset.uri if asset is not None else ""
    else:
        uri = ""
    if not uri:
        return "", ""
    filename = Path(asset.name.replace("\\", "/")).name
    if not filename.lower().endswith((".json", ".pkl")):
        raise ValueError("Label mapping must be a JSON or pickle file.")
    return storage.presigned_get(uri, 14400), filename
