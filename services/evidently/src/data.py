"""Data acquisition and archive handling for drift analysis."""

import json
import hashlib
import re
import zipfile
import time
from pathlib import Path


def load_reference_data(reference_url, model_version_id, temp_root, requests_module, pandas_module, detail):
    if not reference_url:
        raise ValueError("REFERENCE_DATA_URL is not provided")

    local_filename = str(temp_root / f"reference_{model_version_id}.csv")
    if reference_url.startswith("http"):
        detail("[2/4] Downloading reference data from presigned URL...")
        response = requests_module.get(reference_url)
        if response.status_code != 200:
            raise FileNotFoundError(f"Storage returned HTTP {response.status_code}")
        with open(local_filename, "wb") as stream:
            stream.write(response.content)
    else:
        local_filename = reference_url

    frame = pandas_module.read_csv(local_filename)
    detail(f"-> Reference data loaded: {len(frame)} rows")
    return frame


def download_model_metadata(webhook_url, secret, run_id, tenant_id, project_id, version_id, temp_root, requests_module, endpoint_url=None):
    if not run_id:
        return None
    if not endpoint_url:
        if not webhook_url:
            return None
        from urllib.parse import urlsplit, urlunsplit

        parsed = urlsplit(webhook_url)
        endpoint_url = urlunsplit((parsed.scheme, parsed.netloc, f"/internal/drift-runs/{run_id}/model-package-url/", "", ""))
    headers = {
        "Authorization": f"Bearer {secret}", "X-Tenant-ID": tenant_id,
        "X-Project-ID": project_id, "X-Model-Version-ID": version_id,
    }
    deadline = time.monotonic() + 300
    cache = Path(temp_root) / f"model_cache_{run_id}"
    cache.mkdir(parents=True, exist_ok=True)
    archive_path = cache / "package.zip"
    try:
        for attempt in range(2):
            info_response = requests_module.get(endpoint_url, headers=headers, timeout=(10, 30))
            if info_response.status_code == 404:
                return None
            info_response.raise_for_status()
            info = info_response.json()
            if info.get("size_bytes", 0) > 1024**3:
                raise ValueError("Model package exceeds the allowed size")
            package_url = info.get("package_url") or info.get("url")
            with requests_module.get(package_url, stream=True, timeout=(10, 30)) as response:
                if response.status_code == 403 and attempt == 0:
                    archive_path.unlink(missing_ok=True)
                    continue
                response.raise_for_status()
                size = 0
                digest = hashlib.sha256()
                with archive_path.open("wb") as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        size += len(chunk)
                        if size > 1024**3 or time.monotonic() > deadline:
                            raise ValueError("Model package download limit exceeded")
                        digest.update(chunk)
                        stream.write(chunk)
                expected = info.get("checksum", "")
                if expected:
                    if expected.startswith("sha256:"):
                        expected = expected[7:]
                    if len(expected) == 64 and digest.hexdigest() != expected:
                        raise ValueError("Model package checksum mismatch")
                if info.get("size_bytes") and size != info["size_bytes"]:
                    raise ValueError("Model package size mismatch")
            break
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            for member in entries:
                path = Path(member.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in member.filename or (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Unsafe model package")
            models = [member for member in entries if Path(member.filename).name == "MLmodel"]
            if len(models) != 1 or models[0].file_size > 1024**2:
                raise ValueError("Model metadata is unavailable or ambiguous")
            metadata = archive.read(models[0])
        (cache / "MLmodel").write_bytes(metadata)
        return str(cache)
    except Exception:
        import shutil
        shutil.rmtree(cache, ignore_errors=True)
        raise
    finally:
        archive_path.unlink(missing_ok=True)


def load_production_data(
    *,
    connection_url,
    model_version_id,
    max_samples,
    min_samples,
    create_engine,
    sql_text,
    pandas_module,
    detail,
    db_schema="control_plane",
    tenant_id=None,
    project_id=None,
):
    detail(f"[1/4] Fetching Production Logs for Model Version ID: {model_version_id}")
    engine = create_engine(connection_url)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", db_schema):
        raise ValueError("DB_SCHEMA must be a simple PostgreSQL identifier")

    where_clauses = ["version.public_id = CAST(:model_version_id AS uuid)"]
    params = {"model_version_id": str(model_version_id), "lim": max_samples}

    joins = [f'INNER JOIN "{db_schema}"."registry_modelversion" AS version ON version.id = record.model_version_id']

    if project_id or tenant_id:
        joins.append(f'INNER JOIN "{db_schema}"."catalog_modelproject" AS project ON project.id = version.project_id')
    if project_id:
        where_clauses.append("project.public_id = CAST(:project_id AS uuid)")
        params["project_id"] = str(project_id)
    if tenant_id:
        joins.append(
            f'INNER JOIN "{db_schema}"."identity_customuser" AS owner_user ON owner_user.id = project.owner_id'
        )
        where_clauses.append("owner_user.tenant_id = :tenant_id")
        params["tenant_id"] = str(tenant_id)

    joins_sql = "\n        ".join(joins)
    where_sql = " AND ".join(where_clauses)

    query = sql_text(f"""
        SELECT record.features, record.prediction
        FROM "{db_schema}"."production_predictionrecord" AS record
        {joins_sql}
        WHERE {where_sql}
        ORDER BY record.observed_at DESC
        LIMIT :lim
    """)
    with engine.connect() as connection:
        raw_frame = pandas_module.read_sql(
            query,
            connection,
            params=params,
        )
    if len(raw_frame) < min_samples:
        detail(f"Skipping Drift Analysis: Not enough production samples ({len(raw_frame)} < {min_samples})")
        return pandas_module.DataFrame()
    if "features" not in raw_frame.columns:
        return pandas_module.DataFrame()

    features = raw_frame["features"].tolist()
    if isinstance(features[0], str):
        features = [json.loads(value) for value in features]
    production_frame = pandas_module.json_normalize(features)
    if "prediction" in raw_frame.columns:
        production_frame["prediction"] = raw_frame["prediction"].values
    detail(f"-> Production data loaded and JSON normalized: {len(production_frame)} rows")
    return production_frame


def safe_extract_zip(zip_path, destination):
    destination_path = Path(destination)
    destination_path.mkdir(parents=True, exist_ok=True)
    destination_root = destination_path.resolve()
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            resolved = (destination_path / member.filename).resolve()
            if not resolved.is_relative_to(destination_root):
                raise ValueError("Model archive contains an unsafe path.")
            is_symlink = (member.external_attr >> 16) & 0o170000 == 0o120000
            if is_symlink:
                raise ValueError("Model archive contains symbolic links, which are not allowed.")
        archive.extractall(destination_path)
