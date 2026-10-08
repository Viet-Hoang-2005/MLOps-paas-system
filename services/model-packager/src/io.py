"""Artifact transfer, safe extraction, and webhook I/O."""

import hashlib
import json
import tarfile
import time
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
            is_symlink = (member.external_attr >> 16) & 0o170000 == 0o120000
            if is_symlink:
                raise ValueError("Model package contains links, which are not supported.")
        archive.extractall(destination)


def post_webhook(webhook_url, payload, requests_module, headers):
    if not webhook_url:
        raise RuntimeError("Build callback URL is required.")
    key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    delivery_headers = {**headers, "Idempotency-Key": f"build-{payload.get('build_id', '')}-{key}"}
    for attempt in range(3):
        try:
            response = requests_module.post(webhook_url, json=payload, headers=delivery_headers,
                timeout=(2, 5), allow_redirects=False)
            if 200 <= response.status_code < 300:
                return
            retry = response.status_code == 429 or response.status_code >= 500
        except Exception:
            retry = True
        if not retry or attempt == 2:
            break
        time.sleep(2**attempt)
    # Never expose request headers, callback URL or payload through exceptions.
    raise RuntimeError("Build result callback could not be delivered.")
