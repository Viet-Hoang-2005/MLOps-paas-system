"""Artifact transfer, safe extraction, and webhook I/O."""

import tarfile
import zipfile


def download_presigned_file(download_url, destination, requests_module, detail):
    if not download_url:
        raise ValueError("Missing presigned download URL.")
    detail(f"Downloading artifact to {destination.name}...")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests_module.get(download_url, stream=True, timeout=(10, 600)) as response:
        response.raise_for_status()
        with destination.open("wb") as destination_file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    destination_file.write(chunk)
    detail("Download completed.")


def upload_presigned_file(upload_url, source, requests_module, detail):
    if not upload_url:
        raise ValueError("Missing presigned upload URL.")
    detail(f"Uploading {source.name}...")
    with source.open("rb") as source_file:
        response = requests_module.put(upload_url, data=source_file, timeout=(10, 600))
    response.raise_for_status()
    detail("Upload completed.")


def safe_extract_tar(archive_path, destination):
    destination.mkdir(parents=True, exist_ok=True)
    destination_root = destination.resolve()
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            resolved = (destination / member.name).resolve()
            if not resolved.is_relative_to(destination_root):
                raise ValueError("Training artifact contains an unsafe path.")
            if member.islnk() or member.issym():
                raise ValueError("Training artifact contains links, which are not supported.")
        archive.extractall(destination)


def safe_extract_zip(archive_path, destination):
    destination.mkdir(parents=True, exist_ok=True)
    destination_root = destination.resolve()
    with zipfile.ZipFile(archive_path, "r") as archive:
        for member in archive.infolist():
            resolved = (destination / member.filename).resolve()
            if not resolved.is_relative_to(destination_root):
                raise ValueError("Model package contains an unsafe path.")
        archive.extractall(destination)


def post_webhook(webhook_url, payload, requests_module, headers):
    if not webhook_url:
        return
    response = requests_module.post(webhook_url, json=payload, headers=headers, timeout=10)
    if response.status_code >= 400:
        raise RuntimeError(f"Build webhook failed with HTTP {response.status_code}")
