"""Trusted Input preparation. Never imports or executes workspace code."""

import os
import shutil
import time
from pathlib import Path

import requests
from src.io import safe_extract_zip, validate_presigned_url


def prepare():
    root = Path(os.environ.get("PREPARED_INPUT_DIR", "/prepared"))
    root.mkdir(parents=True, exist_ok=True)
    # Repeated init attempts start clean; this volume is job-scoped and not yet
    # mounted by the user process.
    for item in root.iterdir():
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()
    endpoint = os.environ["S3_INPUT_DOWNLOAD_URL"]
    for attempt in range(10):
        try:
            response = requests.post(
                endpoint,
                headers={"Authorization": "Bearer " + os.environ["S3_INPUT_DOWNLOAD_CAPABILITY"]},
                timeout=(3, 15),
            )
            if response.status_code < 500 or attempt == 9:
                break
        except requests.ConnectionError:
            if attempt == 9:
                raise
        time.sleep(2)
    response.raise_for_status()
    uri = response.json()["source_url"]
    validate_presigned_url(uri)
    archive = root / ".input.zip"
    total = 0
    with requests.get(uri, stream=True, timeout=(10, 300)) as download:
        download.raise_for_status()
        with archive.open("wb") as output:
            for chunk in download.iter_content(1024 * 1024):
                total += len(chunk)
                if total > 256 * 1024 * 1024:
                    raise RuntimeError("Input archive exceeds its size limit.")
                output.write(chunk)
    destination = root / "input"
    safe_extract_zip(archive, destination, max_uncompressed_bytes=256 * 1024 * 1024)
    archive.unlink()
    for item in destination.rglob("*"):
        item.chmod(0o555 if item.is_dir() else 0o444)
    destination.chmod(0o555)


if __name__ == "__main__":
    try:
        if os.environ.get("INPUT_CONTRACT", "workspace") == "workspace":
            prepare()
    except Exception as error:
        status = getattr(getattr(error, "response", None), "status_code", None)
        print(
            f"[SYSTEM] Input preparation failed: {type(error).__name__}" + (f" (HTTP {status})" if status else ""),
            flush=True,
        )
        raise SystemExit(1)
