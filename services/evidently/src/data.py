"""Data acquisition and archive handling for drift analysis."""

import json
import os
import re
import shutil
import zipfile
from pathlib import Path
from urllib.parse import urlparse


def load_reference_data(reference_url, model_version_id, temp_root, requests_module,
                        pandas_module, detail):
    if not reference_url:
        raise ValueError("REFERENCE_DATA_URL is not provided")

    is_csv = urlparse(reference_url).path.lower().endswith(".csv")
    local_filename = str(
        temp_root / f"reference_{model_version_id}.{'csv' if is_csv else 'parquet'}"
    )
    if reference_url.startswith("http"):
        detail("[2/4] Downloading reference data from presigned URL...")
        response = requests_module.get(reference_url)
        if response.status_code != 200:
            raise FileNotFoundError(f"Storage returned HTTP {response.status_code}")
        with open(local_filename, "wb") as stream:
            stream.write(response.content)
    else:
        local_filename = reference_url

    frame = (pandas_module.read_csv(local_filename) if local_filename.endswith(".csv")
             else pandas_module.read_parquet(local_filename))
    detail(f"-> Reference data loaded: {len(frame)} rows")
    return frame


def load_production_data(*, connection_url, model_version_id, max_samples,
                         min_samples, create_engine, sql_text, pandas_module, detail,
                         db_schema="control_plane"):
    detail(f"[1/4] Fetching Production Logs for Model Version ID: {model_version_id}")
    engine = create_engine(connection_url)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", db_schema):
        raise ValueError("DB_SCHEMA must be a simple PostgreSQL identifier")
    query = sql_text(f"""
        SELECT record.features, record.prediction
        FROM "{db_schema}"."production_predictionrecord" AS record
        INNER JOIN "{db_schema}"."registry_modelversion" AS version
            ON version.id = record.model_version_id
        WHERE version.public_id = CAST(:model_version_id AS uuid)
        ORDER BY record.observed_at DESC
        LIMIT :lim
    """)
    with engine.connect() as connection:
        raw_frame = pandas_module.read_sql(
            query, connection,
            params={"model_version_id": str(model_version_id), "lim": max_samples},
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
        archive.extractall(destination_path)


def resolve_model_dir(model_uri, *, temp_root, model_version_id, requests_module):
    if not model_uri or model_uri.startswith("models:/"):
        return None
    if os.path.isdir(model_uri):
        for root, _dirs, files in os.walk(model_uri):
            if "MLmodel" in files:
                return root
        return model_uri

    cache_dir = str(temp_root / f"model_cache_{model_version_id}")
    os.makedirs(cache_dir, exist_ok=True)
    zip_path = os.path.join(cache_dir, "model.zip")
    extract_dir = os.path.join(cache_dir, "extracted")
    parsed = urlparse(model_uri)
    if parsed.scheme in ("http", "https"):
        response = requests_module.get(model_uri)
        with open(zip_path, "wb") as stream:
            stream.write(response.content)
    elif os.path.isfile(model_uri):
        shutil.copyfile(model_uri, zip_path)
    else:
        return model_uri
    if os.path.exists(zip_path) and zipfile.is_zipfile(zip_path):
        safe_extract_zip(zip_path, extract_dir)
        for root, _dirs, files in os.walk(extract_dir):
            if "MLmodel" in files:
                return root
        return extract_dir
    return model_uri
