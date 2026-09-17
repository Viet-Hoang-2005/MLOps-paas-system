"""Presigned object transfer, archive extraction, and dependency installation."""

import zipfile
from urllib.parse import urlparse


def validate_presigned_url(uri: str) -> None:
    parsed = urlparse(uri)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("Training runner requires a presigned HTTP(S) URL.")


def download_presigned_url(uri, destination, requests_module, log):
    validate_presigned_url(uri)
    destination.parent.mkdir(parents=True, exist_ok=True)
    log(f"Downloading presigned URL to {destination}")
    with requests_module.get(uri, stream=True, timeout=300) as response:
        response.raise_for_status()
        with open(destination, "wb") as output:
            for chunk in response.iter_content(chunk_size=8192):
                output.write(chunk)


def upload_presigned_url(source, uri, requests_module, log):
    validate_presigned_url(uri)
    log(f"Uploading {source} via presigned PUT URL")
    with open(source, "rb") as handle:
        response = requests_module.put(uri, data=handle, timeout=300)
    if response.status_code not in (200, 201, 204):
        raise RuntimeError(f"Presigned PUT upload failed with HTTP status {response.status_code}")


def request_output_upload_url(endpoint, capability, requests_module):
    validate_presigned_url(endpoint)
    if not capability:
        raise RuntimeError("Missing output upload capability.")
    response = requests_module.post(
        endpoint, headers={"Authorization": f"Bearer {capability}"}, timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Output upload URL request failed with HTTP status {response.status_code}.")
    upload_url = str(response.json().get("upload_url", "")).strip()
    validate_presigned_url(upload_url)
    return upload_url


def safe_extract_zip(zip_path, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        destination_root = destination.resolve()
        for member in archive.infolist():
            member_path = (destination / member.filename).resolve()
            is_symlink = (member.external_attr >> 16) & 0o170000 == 0o120000
            if not member_path.is_relative_to(destination_root) or is_symlink:
                raise RuntimeError("Source zip contains an unsafe path.")
        archive.extractall(destination)


def install_requirements(requirements_path, *, subprocess_module, python_executable,
                         source_dir, detail, log):
    if not requirements_path.exists():
        return
    log("Installing requirements.txt")
    result = subprocess_module.run(
        [python_executable, "-m", "pip", "install", "-r", str(requirements_path)],
        cwd=str(source_dir), capture_output=True, text=True, check=False,
    )
    for line in (result.stdout or "").splitlines():
        detail(line)
    for line in (result.stderr or "").splitlines():
        detail(line)
    if result.returncode != 0:
        raise RuntimeError(f"pip install -r requirements.txt failed with exit code {result.returncode}")
