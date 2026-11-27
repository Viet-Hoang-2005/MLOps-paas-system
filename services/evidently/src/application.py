"""Execute a drift run and publish its reports."""

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import mlflow
import pandas as pd
import redis
import requests
from dotenv import load_dotenv
from evidently import DataDefinition
from requests.adapters import HTTPAdapter
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from src import analysis, config, data, reporting
from src.logging_utils import (
    RuntimeLog,
    bind_context,
    configure,
    get_logger,
    log_event,
    reset_context,
    sanitize,
)
from urllib3.util.retry import Retry

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(dotenv_path=os.path.join(ROOT_DIR, ".env"))

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "mlops_paas_db")
DB_HOST_RO = os.getenv("DB_HOST_RO", "postgres")
DB_SCHEMA = os.getenv("DB_SCHEMA", "control_plane")

TENANT_ID = os.getenv("TENANT_ID")
PROJECT_ID = os.getenv("PROJECT_ID")
MODEL_VERSION_ID = os.getenv("MODEL_VERSION_ID")
MODEL_NAME = os.getenv("MODEL_NAME", PROJECT_ID)
REFERENCE_DATA_URL = os.getenv("REFERENCE_DATA_URL")
CONTROL_PLANE_INTERNAL_URL = os.getenv("CONTROL_PLANE_INTERNAL_URL", "")
CONTROL_PLANE_WEBHOOK_URL = os.getenv("CONTROL_PLANE_WEBHOOK_URL", "")
CONTROL_PLANE_WEBHOOK_SECRET = os.getenv("CONTROL_PLANE_WEBHOOK_SECRET", "super-secret-key")
HTML_S3_URI = os.getenv("HTML_S3_URI", "")
REPORT_JSON_S3_URI = os.getenv("REPORT_JSON_S3_URI", "")
SUMMARY_JSON_S3_URI = os.getenv("SUMMARY_JSON_S3_URI", "")
HTML_PUBLIC_URL = os.getenv("HTML_PUBLIC_URL", "")
DRIFT_RUN_ID = os.getenv("DRIFT_RUN_ID", os.getenv("JOB_ID", ""))
REDIS_URL = os.getenv("REDIS_URL", "")

HTML_UPLOAD_URL = os.getenv("HTML_UPLOAD_URL", "")
REPORT_JSON_UPLOAD_URL = os.getenv("REPORT_JSON_UPLOAD_URL", "")
SUMMARY_JSON_UPLOAD_URL = os.getenv("SUMMARY_JSON_UPLOAD_URL", "")

DRIFT_THRESHOLD = float(os.getenv("DRIFT_THRESHOLD", "0.6"))
MAX_SAMPLES = int(os.getenv("MAX_SAMPLES", "100000"))
MIN_SAMPLES = int(os.getenv("MIN_SAMPLES", "100"))
TEMP_ROOT = Path(os.getenv("MLOPS_TEMP_DIR", tempfile.gettempdir()))


logger = get_logger("evidently")
runtime_log = RuntimeLog(logger)


class RedisLogHandler(logging.Handler):
    """Write sanitized details into the per-run Redis log stream."""

    def __init__(self, redis_url: str, run_id: str):
        super().__init__()
        self.redis_client = redis.from_url(redis_url)
        self.log_key = f"drift_logs:{run_id}"
        self.redis_client.delete(self.log_key)

    def write(self, message: str) -> bool:
        try:
            self.redis_client.rpush(self.log_key, sanitize(message))
            self.redis_client.expire(self.log_key, 3600)
            return True
        except Exception:
            return False

    def emit(self, record):
        try:
            self.write(self.format(record))
        except Exception:
            pass


def setup_logger(run_id: str):
    global runtime_log
    configure("evidently")
    writer = None
    if os.environ.get("LOG_STORAGE_BACKEND", "").strip().lower() != "loki":
        if run_id and REDIS_URL:
            try:
                writer = RedisLogHandler(REDIS_URL, run_id).write
            except Exception as exc:
                log_event(
                    logger,
                    logging.WARNING,
                    "runtime_log_unavailable",
                    "Could not connect to Redis for drift log streaming",
                    reason=sanitize(str(exc)),
                )
    runtime_log = RuntimeLog(logger, writer=writer)
    return logger


def validate_runtime_config():
    config.validate(DRIFT_THRESHOLD, TENANT_ID, PROJECT_ID, MODEL_VERSION_ID)


# 1. Táº£i Reference Data
def load_reference_data():
    return data.load_reference_data(
        REFERENCE_DATA_URL,
        MODEL_VERSION_ID,
        TEMP_ROOT,
        requests,
        pd,
        runtime_log.detail,
    )


# 2. Truy váº¥n dá»¯ liá»‡u Production Data
def load_production_data():
    return data.load_production_data(
        connection_url=URL.create(
            "postgresql+psycopg",
            username=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST_RO,
            port=DB_PORT,
            database=DB_NAME,
        ),
        model_version_id=MODEL_VERSION_ID,
        max_samples=MAX_SAMPLES,
        min_samples=MIN_SAMPLES,
        create_engine=create_engine,
        sql_text=text,
        pandas_module=pd,
        detail=runtime_log.detail,
        db_schema=DB_SCHEMA,
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
    )


# HÃ m há»— trá»£ táº£i model trÃªn S3
def resolve_model_dir():
    endpoint_url = None
    if CONTROL_PLANE_INTERNAL_URL and DRIFT_RUN_ID:
        endpoint_url = f"{CONTROL_PLANE_INTERNAL_URL.rstrip('/')}/internal/drift-runs/{DRIFT_RUN_ID}/model-package-url/"
    return data.download_model_metadata(
        CONTROL_PLANE_WEBHOOK_URL,
        CONTROL_PLANE_WEBHOOK_SECRET,
        DRIFT_RUN_ID,
        TENANT_ID,
        PROJECT_ID,
        MODEL_VERSION_ID,
        TEMP_ROOT,
        requests,
        endpoint_url=endpoint_url,
    )


def safe_extract_zip(zip_path, destination):
    return data.safe_extract_zip(zip_path, destination)


LABEL_COLUMNS = ("target", "Target", "label", "Label", "class", "Class")
NON_FEATURE_COLUMNS = {
    *LABEL_COLUMNS,
    "prediction",
    "timestamp",
    "created_at",
    "prediction_id",
    "id",
    "model_version_id",
    "project_id",
    "tenant_id",
    "endpoint_url",
    "request_id",
    "status_code",
    "latency_ms",
    "confidence",
    "raw_payload",
}


def get_data_definition(reference_df):
    """Use named model inputs when available and infer types from the reference otherwise."""
    resolved_uri = None
    try:
        resolved_uri = resolve_model_dir()
        if resolved_uri:
            try:
                signature = mlflow.models.get_model_info(resolved_uri).signature
                inputs = getattr(signature, "inputs", None)
                types = {inp.name: getattr(inp.type, "name", str(inp.type)) for inp in (inputs or ()) if inp.name}
                if types:
                    runtime_log.detail("Data definition generated from MLflow model package signature")
                    numerical = [name for name, kind in types.items() if kind in {"integer", "long", "float", "double"}]
                    return DataDefinition(
                        numerical_columns=numerical, categorical_columns=[name for name in types if name not in numerical]
                    )
                runtime_log.event(
                    logging.WARNING,
                    "model_signature_unavailable",
                    "MLflow signature is empty or missing in model package",
                    reason="SignatureMissing",
                )
            finally:
                import shutil

                shutil.rmtree(resolved_uri, ignore_errors=True)
    except Exception as exc:
        runtime_log.event(
            logging.WARNING,
            "model_signature_unavailable",
            "MLflow signature extraction failed",
            reason=type(exc).__name__,
        )

    runtime_log.detail("Data definition inferred from reference dataset")
    features = reference_df.drop(columns=list(NON_FEATURE_COLUMNS), errors="ignore")
    numerical = features.select_dtypes(include="number").columns.tolist()
    return DataDefinition(
        numerical_columns=numerical,
        categorical_columns=[name for name in features if name not in numerical],
    )


def prepare_prediction(reference_df, production_df):
    if "prediction" not in production_df:
        return None
    if "prediction" not in reference_df:
        label = next((column for column in LABEL_COLUMNS if column in reference_df), None)
        if label is None:
            return None
        reference_df["prediction"] = reference_df[label]
    align_prediction_types(reference_df, production_df)
    return "prediction"


def align_prediction_types(reference_df, production_df):
    """Give `prediction` the same kind of values on both sides.

    Production stores predictions as text while a reference label is usually numeric;
    comparing the two would report drift between identical distributions.
    """
    if "prediction" not in reference_df.columns or "prediction" not in production_df.columns:
        return
    reference = reference_df["prediction"]
    if pd.api.types.is_numeric_dtype(reference) and not pd.api.types.is_bool_dtype(reference):
        production_df["prediction"] = pd.to_numeric(production_df["prediction"], errors="coerce")
    else:
        reference_df["prediction"] = reference.astype("string")
        production_df["prediction"] = production_df["prediction"].astype("string")


def run_drift_analysis(reference_df, production_df, definition):
    runtime_log.detail("[4/4] Running Evidently Data Drift & Data Quality analysis...")
    reference_df = reference_df.copy(deep=False)
    production_df = production_df.copy(deep=False)
    prediction = prepare_prediction(reference_df, production_df)

    numerical = definition.numerical_columns or []
    categorical = definition.categorical_columns or []
    expected_features = [column for column in [*numerical, *categorical] if column not in NON_FEATURE_COLUMNS]
    if not expected_features:
        raise ValueError("No input features defined for drift analysis.")

    missing_features = sorted(set(expected_features) - set(production_df))
    extra_features = sorted(set(production_df) - set(reference_df) - NON_FEATURE_COLUMNS)
    common_features = [column for column in expected_features if column in production_df]
    missing_reference = sorted(set(expected_features) - set(reference_df))
    if missing_reference:
        raise ValueError(f"Reference data lacks expected features: {', '.join(missing_reference)}.")

    if missing_features:
        runtime_log.event(
            logging.WARNING,
            "drift_missing_features",
            "Production data is missing expected features",
            count=len(missing_features),
        )
    if extra_features:
        runtime_log.detail(f"Production data contains {len(extra_features)} extra features")

    high_null_features = []
    for column in common_features:
        null_rate = float(production_df[column].isna().mean())
        if null_rate >= 0.20:
            high_null_features.append({"feature": column, "null_rate": round(null_rate, 4)})

    if high_null_features:
        runtime_log.event(
            logging.WARNING,
            "drift_high_null_features",
            "High null rates detected",
            count=len(high_null_features),
        )

    numerical_columns = [column for column in common_features if column in numerical]
    categorical_columns = [column for column in common_features if column in categorical]
    if prediction:
        reference_prediction = reference_df[prediction]
        if pd.api.types.is_numeric_dtype(reference_prediction) and reference_prediction.nunique() > 2:
            numerical_columns.append(prediction)
        else:
            categorical_columns.append(prediction)
    shared_definition = DataDefinition(numerical_columns=numerical_columns, categorical_columns=categorical_columns)
    snapshot, result_dict, rows = analysis.build_report(
        reference_df, production_df, common_features, shared_definition, prediction, DRIFT_THRESHOLD
    )

    stat_drifted_feature_names = [column for column in common_features if rows[column]["drift_detected"]]
    prediction_drift = rows[prediction]["drift_detected"] if prediction else None
    all_drifted_features = sorted(set(stat_drifted_feature_names) | set(missing_features))
    total_expected_count = len(expected_features)
    total_drifted_count = len(all_drifted_features)
    effective_drift_share = (total_drifted_count / total_expected_count) if total_expected_count > 0 else 0.0

    has_schema_mismatch = len(missing_features) > 0
    dataset_drift = (effective_drift_share >= DRIFT_THRESHOLD) or has_schema_mismatch

    data_quality = {
        "status": "alert" if has_schema_mismatch else ("warning" if high_null_features else "healthy"),
        "has_schema_mismatch": has_schema_mismatch,
        "missing_features": missing_features,
        "missing_features_count": len(missing_features),
        "extra_features": extra_features,
        "extra_features_count": len(extra_features),
        "high_null_features": high_null_features,
        "expected_features_count": total_expected_count,
        "common_features_count": len(common_features),
    }

    summary = {
        "report_schema_version": result_dict["schema_version"],
        "evidently_version": result_dict["evidently_version"],
        "tenant_id": TENANT_ID,
        "project_id": PROJECT_ID,
        "model_version_id": MODEL_VERSION_ID,
        "share_drifted_features": round(effective_drift_share, 4),
        "drift_score": round(effective_drift_share, 4),
        "dataset_drift": dataset_drift,
        "has_drift": dataset_drift,
        "drift_threshold": DRIFT_THRESHOLD,
        "number_of_drifted_features": total_drifted_count,
        "number_of_features": total_expected_count,
        "drifted_feature_names": all_drifted_features,
        "statistical_drifted_features": stat_drifted_feature_names,
        "prediction_drift": prediction_drift,
        "missing_features": missing_features,
        "extra_features": extra_features,
        "data_quality": data_quality,
        "production_records": len(production_df),
        "samples": len(production_df),
    }
    summary["report_artifacts"] = save_drift_report(snapshot, result_dict, summary)

    runtime_log.event(
        logging.INFO,
        "drift_analysis_summary",
        (
            f"Data drift analysis completed: drift={dataset_drift}, "
            f"share={effective_drift_share:.2%}, features={total_drifted_count}/{total_expected_count}, "
            f"quality={data_quality['status']}"
        ),
        drift_detected=dataset_drift,
        drift_share=round(effective_drift_share, 4),
        features_count=total_expected_count,
        count=total_drifted_count,
        reference_samples=len(reference_df),
        production_samples=len(production_df),
        status=data_quality["status"],
        reason=(
            f"threshold={DRIFT_THRESHOLD}; common={len(common_features)}; "
            f"missing={len(missing_features)}; extra={len(extra_features)}; "
            f"high_null={len(high_null_features)}"
        ),
    )

    return summary


# 6. LÆ°u bÃ¡o cÃ¡o drift
def save_drift_report(snapshot, result_dict, summary):
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_dir = str(TEMP_ROOT / "drift_reports" / str(TENANT_ID) / str(MODEL_NAME) / run_id)
    os.makedirs(report_dir, exist_ok=True)

    html_path = os.path.join(report_dir, "report.html")
    result_json_path = os.path.join(report_dir, "report.json")
    summary_json_path = os.path.join(report_dir, "summary.json")

    if snapshot is not None:
        snapshot.save_html(html_path)
    else:
        Path(html_path).write_text(
            '<!doctype html><html lang="en"><meta charset="utf-8"><title>Drift report</title>'
            "<h1>Schema mismatch</h1><p>No input features available for statistical comparison. "
            "See the report summary for the missing features.</p></html>",
            encoding="utf-8",
        )
    with open(result_json_path, "w", encoding="utf-8") as fp:
        json.dump(result_dict, fp, ensure_ascii=False, indent=2, allow_nan=False)
    with open(summary_json_path, "w", encoding="utf-8") as fp:
        json.dump(summary, fp, ensure_ascii=False, indent=2, default=str)

    artifacts = {
        "local_html_path": html_path,
        "local_report_json_path": result_json_path,
        "local_summary_json_path": summary_json_path,
    }

    if not HTML_UPLOAD_URL:
        runtime_log.event(
            logging.WARNING,
            "drift_report_upload_skipped",
            "Upload URLs not provided. Skipping upload.",
        )
        return artifacts

    uploads = [
        (html_path, HTML_UPLOAD_URL, "text/html"),
        (result_json_path, REPORT_JSON_UPLOAD_URL, "application/json"),
        (summary_json_path, SUMMARY_JSON_UPLOAD_URL, "application/json"),
    ]

    configured_uploads = [item for item in uploads if item[1]]
    uploaded_count = 0
    max_retries = 3
    is_testing = bool(os.environ.get("PYTEST_CURRENT_TEST"))

    for local_path, upload_url, content_type in uploads:
        if upload_url:
            last_err = None
            for attempt in range(max_retries):
                try:
                    with open(local_path, "rb") as f:
                        resp = requests.put(upload_url, data=f, headers={"Content-Type": content_type}, timeout=(5, 60))
                        resp.raise_for_status()
                    uploaded_count += 1
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    if attempt < max_retries - 1 and not is_testing:
                        time.sleep(0.5 * (attempt + 1))
            if last_err is not None:
                runtime_log.event(
                    logging.ERROR,
                    "drift_report_upload_failed",
                    "Failed to upload drift report",
                    reason=sanitize(str(last_err)),
                )

    all_uploads_succeeded = uploaded_count == len(configured_uploads)
    if all_uploads_succeeded:
        artifacts.update(
            {
                "s3_report_prefix": "",
                "html_s3_uri": HTML_S3_URI,
                "report_json_s3_uri": REPORT_JSON_S3_URI,
                "summary_json_s3_uri": SUMMARY_JSON_S3_URI,
                "html_url": HTML_PUBLIC_URL,
            }
        )
    runtime_log.detail(f"Drift report upload attempts finished: {uploaded_count}/{len(uploads)} files uploaded.")

    summary_with_artifacts = {**summary, "report_artifacts": artifacts}
    with open(summary_json_path, "w", encoding="utf-8") as fp:
        json.dump(summary_with_artifacts, fp, ensure_ascii=False, indent=2, default=str)

    # Refresh summary.json on S3
    if SUMMARY_JSON_UPLOAD_URL and all_uploads_succeeded:
        refresh_err = None
        for attempt in range(max_retries):
            try:
                with open(summary_json_path, "rb") as f:
                    resp = requests.put(
                        SUMMARY_JSON_UPLOAD_URL,
                        data=f,
                        headers={"Content-Type": "application/json"},
                        timeout=(5, 60),
                    )
                    resp.raise_for_status()
                refresh_err = None
                break
            except Exception as e:
                refresh_err = e
                if attempt < max_retries - 1 and not is_testing:
                    time.sleep(0.5 * (attempt + 1))
        if refresh_err is not None:
            runtime_log.event(
                logging.ERROR,
                "drift_summary_upload_failed",
                "Failed to refresh summary report",
                reason=sanitize(str(refresh_err)),
            )
    elif SUMMARY_JSON_UPLOAD_URL and not all_uploads_succeeded:
        runtime_log.event(
            logging.ERROR,
            "drift_summary_upload_failed",
            "Skipping refresh of summary report due to previous upload failures",
            reason="previous_uploads_failed",
        )

    return artifacts


# 7. Gá»­i káº¿t quáº£ vá» Django Webhook
def trigger_django_webhook(drift_summary):
    def on_error(message, **fields):
        if "reason" in fields:
            fields["reason"] = sanitize(fields["reason"])
        runtime_log.event(logging.ERROR, "drift_callback_failed", message, **fields)

    reporting.trigger_webhook(
        requests_module=requests,
        retry_factory=Retry,
        adapter_factory=HTTPAdapter,
        webhook_url=CONTROL_PLANE_WEBHOOK_URL,
        webhook_secret=CONTROL_PLANE_WEBHOOK_SECRET,
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        model_version_id=MODEL_VERSION_ID,
        drift_summary=drift_summary,
        threshold=DRIFT_THRESHOLD,
        detail=runtime_log.detail,
        on_error=on_error,
    )


def _run():
    try:
        validate_runtime_config()
    except ValueError as exc:
        runtime_log.event(
            logging.ERROR,
            "drift_config_invalid",
            "Invalid drift runtime configuration",
            reason=sanitize(str(exc)),
        )
        return 1

    try:
        production_df = load_production_data()
    except Exception as e:
        runtime_log.event(
            logging.ERROR,
            "drift_production_data_failed",
            "Failed to load production data",
            reason=sanitize(str(e)),
            exc_info=True,
        )
        return 1

    if len(production_df) < MIN_SAMPLES:
        runtime_log.event(
            logging.INFO,
            "drift_analysis_skipped",
            "Insufficient production samples",
            samples=len(production_df),
            reason=f"minimum_samples={MIN_SAMPLES}",
        )
        if SUMMARY_JSON_UPLOAD_URL:
            try:
                requests.put(
                    SUMMARY_JSON_UPLOAD_URL,
                    data=json.dumps(
                        {
                            "status": "skipped",
                            "reason": f"Insufficient production samples ({len(production_df)} < {MIN_SAMPLES})",
                            "samples": len(production_df),
                            "minimum_samples": MIN_SAMPLES,
                            "dataset_drift": False,
                            "has_drift": False,
                            "drift_score": None,
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                ).raise_for_status()
            except Exception as exc:
                runtime_log.event(
                    logging.WARNING,
                    "drift_skipped_summary_upload_failed",
                    "Failed to upload skipped summary JSON",
                    reason=sanitize(str(exc)),
                )
        if CONTROL_PLANE_WEBHOOK_URL:
            skipped_summary = {
                "status": "skipped",
                "reason": f"Insufficient production samples ({len(production_df)} < {MIN_SAMPLES})",
                "samples": len(production_df),
                "minimum_samples": MIN_SAMPLES,
                "dataset_drift": False,
                "has_drift": False,
                "drift_score": None,
            }
            trigger_django_webhook(skipped_summary)
        return 0

    try:
        reference_df = load_reference_data()
    except Exception as e:
        runtime_log.event(
            logging.WARNING,
            "drift_reference_fallback",
            "Reference data unavailable. Generating baseline from oldest 50% of production data",
            reason=sanitize(str(e)),
        )
        half_idx = len(production_df) // 2
        reference_df = production_df.iloc[half_idx:].copy()
        production_df = production_df.iloc[:half_idx].copy()

    try:
        definition = get_data_definition(reference_df)
        drift_summary = run_drift_analysis(reference_df, production_df, definition)
    except Exception as e:
        runtime_log.event(
            logging.ERROR,
            "drift_analysis_failed",
            "Drift analysis failed",
            reason=sanitize(str(e)),
            exc_info=True,
        )
        return 1

    artifacts = drift_summary.get("report_artifacts", {})
    if HTML_UPLOAD_URL and not artifacts.get("html_s3_uri"):
        runtime_log.event(
            logging.ERROR,
            "drift_upload_incomplete",
            "Required S3 drift report artifacts failed to upload",
        )
        return 1

    trigger_django_webhook(drift_summary)
    return 0


def main():
    started = time.monotonic()
    setup_logger(DRIFT_RUN_ID)
    tokens = bind_context(
        drift_run_id=DRIFT_RUN_ID,
        project_id=PROJECT_ID,
        model_version_id=MODEL_VERSION_ID,
        tenant_id=TENANT_ID,
    )
    try:
        runtime_log.event(
            logging.INFO,
            "drift_execution_started",
            "Drift runner execution started",
            duration_ms=0,
        )
        result = _run()
        runtime_log.event(
            logging.INFO,
            "drift.execution.exited",
            "Drift runner exited",
            exit_code=result,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
        )
        return result
    except Exception as exc:
        runtime_log.event(
            logging.ERROR,
            "drift_execution_failed",
            "Drift runner execution failed",
            reason=sanitize(str(exc)),
            exc_info=True,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
        )
        raise
    finally:
        reset_context(tokens)
