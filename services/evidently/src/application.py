# main.py: Phát hiện Data Drift (Sử dụng Evidently 0.4.15 Stable)
import os
import sys
import json
import logging
from src.logging_utils import RuntimeLog, bind_context, configure, get_logger, log_event, reset_context, sanitize
import mlflow
import zipfile
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
import redis
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timezone
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset
from evidently.pipeline.column_mapping import ColumnMapping
from src import analysis, config, data, reporting

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
MODEL_URI = os.getenv("MODEL_URI", f"models:/{MODEL_NAME}/Production")
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
    if run_id and REDIS_URL:
        try:
            writer = RedisLogHandler(REDIS_URL, run_id).write
        except Exception as exc:
            log_event(logger, logging.WARNING, "runtime_log_unavailable",
                      "Could not connect to Redis for drift log streaming", reason=sanitize(str(exc)))
    runtime_log = RuntimeLog(logger, writer=writer)
    return logger

def validate_runtime_config():
    config.validate(DRIFT_THRESHOLD, TENANT_ID, PROJECT_ID, MODEL_VERSION_ID)

# 1. Tải Reference Data
def load_reference_data():
    return data.load_reference_data(
        REFERENCE_DATA_URL, MODEL_VERSION_ID, TEMP_ROOT, requests, pd, runtime_log.detail,
    )

# 2. Truy vấn dữ liệu Production Data
def load_production_data():
    return data.load_production_data(
        connection_url=f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST_RO}:{DB_PORT}/{DB_NAME}",
        model_version_id=MODEL_VERSION_ID, max_samples=MAX_SAMPLES, min_samples=MIN_SAMPLES,
        create_engine=create_engine, sql_text=text, pandas_module=pd, detail=runtime_log.detail, db_schema=DB_SCHEMA,
    )

# Hàm hỗ trợ tải model trên S3
def resolve_model_dir(model_uri):
    return data.resolve_model_dir(
        model_uri, temp_root=TEMP_ROOT, model_version_id=MODEL_VERSION_ID,
        requests_module=requests,
    )


def safe_extract_zip(zip_path, destination):
    return data.safe_extract_zip(zip_path, destination)

# 3. Trích xuất column mapping từ MLFlow
def get_column_mapping(reference_df, production_df):
    runtime_log.detail(f"[3/4] Extracting Model Signature from MLflow: {MODEL_URI}")
    column_mapping = ColumnMapping()
    has_signature = False

    if mlflow is not None:
        try:
            resolved_uri = resolve_model_dir(MODEL_URI)
            if resolved_uri:
                runtime_log.detail(f"Resolved model directory: {resolved_uri}")
                model_info = mlflow.models.get_model_info(resolved_uri)
                signature = model_info.signature
                if signature and signature.inputs:
                    num_cols = []
                    cat_cols = []
                    for inp in signature.inputs:
                        if inp.type in ["integer", "long", "float", "double"]:
                            num_cols.append(inp.name)
                        else:
                            cat_cols.append(inp.name)
                    column_mapping.numerical_features = num_cols
                    column_mapping.categorical_features = cat_cols
                    has_signature = True
                    runtime_log.detail(f"-> MLflow Signature: {len(num_cols)} numerical, {len(cat_cols)} categorical.")
        except Exception as e:
            runtime_log.event(logging.WARNING, "model_signature_unavailable", "MLflow signature extraction failed", reason=sanitize(str(e)))

    # Fallback: Auto-infer feature types from actual DataFrame structure
    if not has_signature:
        runtime_log.detail("-> Fallback: Auto-infer feature types from actual DataFrame structure...")
        ignore_cols = {
            "prediction", "target", "Target", "label", "Label", "class", "Class",
            "timestamp", "model_version_id", "project_id", "tenant_id",
        }
        feature_cols = [c for c in production_df.columns if c not in ignore_cols]
        num_cols = production_df[feature_cols].select_dtypes(include=["int64", "float64", "int32", "float32"]).columns.tolist()
        cat_cols = production_df[feature_cols].select_dtypes(include=["object", "category", "bool"]).columns.tolist()
        column_mapping.numerical_features = num_cols
        column_mapping.categorical_features = cat_cols
        runtime_log.detail(f"Column: {len(num_cols)} numerical, {len(cat_cols)} categorical.")

    if "prediction" in production_df.columns:
        if "prediction" not in reference_df.columns:
            for cand in ["target", "Target", "label", "Label", "class", "Class"]:
                if cand in reference_df.columns:
                    reference_df["prediction"] = reference_df[cand].values
                    runtime_log.detail(f"Mapped column '{cand}' of Reference to 'prediction'.")
                    break
        if "prediction" in reference_df.columns:
            column_mapping.prediction = "prediction"

    for cand in ["target", "Target", "label", "Label", "class", "Class"]:
        if cand in reference_df.columns and cand in production_df.columns:
            column_mapping.target = cand
            break

    return column_mapping

# 4. Lọc column mapping
def filter_column_mapping(column_mapping, common_cols):
    return analysis.filter_column_mapping(column_mapping, common_cols, ColumnMapping)

# 5. Phân tích Data drift & Data Quality (Evidently 0.4.15)
def run_drift_analysis(reference_df, production_df, column_mapping):
    runtime_log.detail("[4/4] Running Evidently AI Data Drift & Data Quality analysis...")

    ignore_cols = {
        "prediction", "target", "Target", "label", "Label", "class", "Class",
        "timestamp", "created_at", "prediction_id", "id", "model_version_id",
        "project_id", "tenant_id", "endpoint_url", "request_id", "status_code",
        "latency_ms", "confidence", "raw_payload",
    }

    # 1. Xác định tập đặc trưng kỳ vọng từ Reference Data / Column Mapping
    if column_mapping.numerical_features or column_mapping.categorical_features:
        expected_features = set((column_mapping.numerical_features or []) + (column_mapping.categorical_features or []))
    else:
        expected_features = set(c for c in reference_df.columns if c not in ignore_cols)

    production_features = set(c for c in production_df.columns if c not in ignore_cols)

    # 2. Phát hiện bất thường Schema / Data Quality (Missing Features & Extra Features)
    missing_features = sorted(list(expected_features - set(production_df.columns)))
    extra_features = sorted(list(production_features - set(reference_df.columns)))

    if missing_features:
        runtime_log.event(logging.WARNING, "drift_missing_features", "Production data is missing expected features", count=len(missing_features))
    if extra_features:
        runtime_log.detail(f"Production data contains {len(extra_features)} extra features")

    # 3. Lấy các cột chung để chạy kiểm định thống kê Evidently
    common_cols = [col for col in reference_df.columns if col in production_df.columns]
    if len(common_cols) == 0:
        raise ValueError("No common columns found between reference and production datasets.")

    # 4. Kiểm tra tỷ lệ giá trị null bất thường trên các cột chung
    high_null_features = []
    for col in common_cols:
        if col not in ignore_cols and col in production_df.columns:
            null_rate = float(production_df[col].isnull().mean())
            if null_rate >= 0.20:
                high_null_features.append({"feature": col, "null_rate": round(null_rate, 4)})

    if high_null_features:
        runtime_log.event(logging.WARNING, "drift_high_null_features", "High null rates detected", count=len(high_null_features))

    ref_clean = reference_df[common_cols]
    prod_clean = production_df[common_cols]
    filtered_mapping = filter_column_mapping(column_mapping, common_cols)

    try:
        report = Report(metrics=[DataDriftPreset(drift_share=DRIFT_THRESHOLD)])
    except TypeError:
        runtime_log.event(logging.WARNING, "drift_threshold_compatibility", "Evidently DataDriftPreset does not accept drift_share. Applying threshold in summary only.")
        report = Report(metrics=[DataDriftPreset()])
    report.run(reference_data=ref_clean, current_data=prod_clean, column_mapping=filtered_mapping)

    result_dict = report.as_dict()
    dataset_drift_metrics = {}
    data_drift_table = {}

    for item in result_dict.get('metrics', []):
        result_data = item.get('result', {})
        if 'dataset_drift' in result_data and 'share_of_drifted_columns' in result_data:
            dataset_drift_metrics = result_data
        if 'drift_by_columns' in result_data:
            data_drift_table = result_data

    drift_by_columns = data_drift_table.get('drift_by_columns', {})
    stat_drifted_feature_names = []
    for col_name, col_data in drift_by_columns.items():
        if col_data.get('drift_detected', False):
            stat_drifted_feature_names.append(col_name)

    # 5. Tổng hợp độ trôi dạt tổng thể (Statistical Drift + Missing Features)
    all_drifted_features = sorted(list(set(stat_drifted_feature_names) | set(missing_features)))
    total_expected_count = len(expected_features) if expected_features else len(common_cols)
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
        "common_features_count": len(common_cols),
    }

    summary = {
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
        "missing_features": missing_features,
        "extra_features": extra_features,
        "data_quality": data_quality,
    }
    summary["report_artifacts"] = save_drift_report(report, result_dict, summary)

    runtime_log.event(
        logging.INFO, "drift_analysis_summary",
        (f"Data drift analysis completed: drift={dataset_drift}, "
         f"share={effective_drift_share:.2%}, features={total_drifted_count}/{total_expected_count}, "
         f"quality={data_quality['status']}"),
        drift_detected=dataset_drift, drift_share=round(effective_drift_share, 4),
        features_count=total_expected_count, count=total_drifted_count,
        reference_samples=len(reference_df), production_samples=len(production_df),
        status=data_quality["status"],
        reason=(f"threshold={DRIFT_THRESHOLD}; common={len(common_cols)}; "
                f"missing={len(missing_features)}; extra={len(extra_features)}; "
                f"high_null={len(high_null_features)}"),
    )

    return summary

# 6. Lưu báo cáo drift
def save_drift_report(report, result_dict, summary):
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_dir = str(TEMP_ROOT / "drift_reports" / str(TENANT_ID) / str(MODEL_NAME) / run_id)
    os.makedirs(report_dir, exist_ok=True)

    html_path = os.path.join(report_dir, "report.html")
    result_json_path = os.path.join(report_dir, "report.json")
    summary_json_path = os.path.join(report_dir, "summary.json")

    report.save_html(html_path)
    with open(result_json_path, "w", encoding="utf-8") as fp:
        json.dump(result_dict, fp, ensure_ascii=False, indent=2, default=str)
    with open(summary_json_path, "w", encoding="utf-8") as fp:
        json.dump(summary, fp, ensure_ascii=False, indent=2, default=str)

    artifacts = {
        "local_html_path": html_path,
        "local_report_json_path": result_json_path,
        "local_summary_json_path": summary_json_path,
    }

    if not HTML_UPLOAD_URL:
        runtime_log.event(logging.WARNING, "drift_report_upload_skipped", "Upload URLs not provided. Skipping upload.")
        return artifacts

    uploads = [
        (html_path, HTML_UPLOAD_URL, "text/html"),
        (result_json_path, REPORT_JSON_UPLOAD_URL, "application/json"),
        (summary_json_path, SUMMARY_JSON_UPLOAD_URL, "application/json"),
    ]

    uploaded_count = 0
    for local_path, upload_url, content_type in uploads:
        if upload_url:
            try:
                with open(local_path, "rb") as f:
                    resp = requests.put(upload_url, data=f, headers={"Content-Type": content_type})
                    resp.raise_for_status()
                uploaded_count += 1
            except Exception as e:
                runtime_log.event(logging.ERROR, "drift_report_upload_failed", "Failed to upload drift report", reason=sanitize(str(e)))

    artifacts.update({
        "s3_report_prefix": "",
        "html_s3_uri": HTML_S3_URI,
        "report_json_s3_uri": REPORT_JSON_S3_URI,
        "summary_json_s3_uri": SUMMARY_JSON_S3_URI,
        "html_url": HTML_PUBLIC_URL,
    })
    runtime_log.detail(f"Drift report upload attempts finished: {uploaded_count}/{len(uploads)} files uploaded.")

    summary_with_artifacts = {**summary, "report_artifacts": artifacts}
    with open(summary_json_path, "w", encoding="utf-8") as fp:
        json.dump(summary_with_artifacts, fp, ensure_ascii=False, indent=2, default=str)
    
    # Refresh summary.json on S3
    if SUMMARY_JSON_UPLOAD_URL:
        try:
            with open(summary_json_path, "rb") as f:
                resp = requests.put(SUMMARY_JSON_UPLOAD_URL, data=f, headers={"Content-Type": "application/json"})
                resp.raise_for_status()
        except Exception as e:
            runtime_log.event(logging.ERROR, "drift_summary_upload_failed", "Failed to refresh summary report", reason=sanitize(str(e)))

    return artifacts


# 7. Gửi kết quả về Django Webhook
def trigger_django_webhook(drift_summary):
    def on_error(message, **fields):
        if "reason" in fields:
            fields["reason"] = sanitize(fields["reason"])
        runtime_log.event(logging.ERROR, "drift_callback_failed", message, **fields)

    reporting.trigger_webhook(
        requests_module=requests, retry_factory=Retry, adapter_factory=HTTPAdapter,
        webhook_url=CONTROL_PLANE_WEBHOOK_URL, webhook_secret=CONTROL_PLANE_WEBHOOK_SECRET,
        tenant_id=TENANT_ID, project_id=PROJECT_ID, model_version_id=MODEL_VERSION_ID,
        drift_summary=drift_summary, threshold=DRIFT_THRESHOLD,
        detail=runtime_log.detail, on_error=on_error,
    )


def _run():
    try:
        validate_runtime_config()
    except ValueError as exc:
        runtime_log.event(logging.ERROR, "drift_config_invalid", "Invalid drift runtime configuration", reason=sanitize(str(exc)))
        return 1

    try:
        production_df = load_production_data()
    except Exception as e:
        runtime_log.event(logging.ERROR, "drift_production_data_failed", "Failed to load production data", reason=sanitize(str(e)), exc_info=True)
        return 1

    if len(production_df) < MIN_SAMPLES:
        runtime_log.event(logging.INFO, "drift_analysis_skipped", "Insufficient production samples",
                          samples=len(production_df), reason=f"minimum_samples={MIN_SAMPLES}")
        return 0

    try:
        reference_df = load_reference_data()
    except Exception as e:
        runtime_log.event(logging.WARNING, "drift_reference_fallback", "Reference data unavailable. Generating baseline from oldest 50% of production data", reason=sanitize(str(e)))
        half_idx = len(production_df) // 2
        reference_df = production_df.iloc[half_idx:].copy()
        production_df = production_df.iloc[:half_idx].copy()  

    column_mapping = get_column_mapping(reference_df, production_df)

    try:
        drift_summary = run_drift_analysis(reference_df, production_df, column_mapping)
    except Exception as e:
        runtime_log.event(logging.ERROR, "drift_analysis_failed", "Drift analysis failed", reason=sanitize(str(e)), exc_info=True)
        return 1

    trigger_django_webhook(drift_summary)
    return 0


def main():
    started = time.monotonic()
    setup_logger(DRIFT_RUN_ID)
    tokens = bind_context(drift_run_id=DRIFT_RUN_ID, project_id=PROJECT_ID,
                          model_version_id=MODEL_VERSION_ID, tenant_id=TENANT_ID)
    try:
        runtime_log.event(logging.INFO, "drift_execution_started", "Drift runner execution started", duration_ms=0)
        result = _run()
        runtime_log.event(
            logging.INFO, "drift.execution.exited", "Drift runner exited", exit_code=result,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
        )
        return result
    except Exception as exc:
        runtime_log.event(logging.ERROR, "drift_execution_failed", "Drift runner execution failed",
                          reason=sanitize(str(exc)), exc_info=True,
                          duration_ms=round((time.monotonic() - started) * 1000, 3))
        raise
    finally:
        reset_context(tokens)
