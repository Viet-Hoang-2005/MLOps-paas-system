import os
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import redis
import base64
import mlflow
import requests
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

WORKSPACE = Path("/workspace")
SOURCE_DIR = WORKSPACE / "source"
INPUT_TRAIN_DIR = WORKSPACE / "input" / "train"
MODEL_DIR = WORKSPACE / "model"
OUTPUT_DIR = WORKSPACE / "output"
MLOPS_DIR_NAME = "_mlops"
RUNNER_VERSION = "mlops-metadata-bundle-v1"
MODEL_FILE_EXTENSIONS = {".pkl", ".joblib", ".xgb"}
CHECKPOINT_EXTENSIONS = {".pt", ".pth", ".ckpt", ".h5", ".onnx", ".keras"}
METADATA_EXTENSIONS = {".json", ".yaml", ".yml", ".txt"}
INSIGHTS_INPUT_FILES = (
    ("model_insights.json", ""),
    ("feature_importance.json", "feature_importance"),
    ("coefficients.json", "coefficients"),
    ("weights_summary.json", "weights_summary"),
)
MAX_MODEL_INSIGHT_ITEMS = 500


def log_to_redis(message: str) -> None:
    job_id = os.environ.get("TRAINING_JOB_ID", "").strip()
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not job_id or not redis_url:
        return
    try:
        r = redis.from_url(redis_url)
        r.rpush(f"training_logs:{job_id}", message)
        r.expire(f"training_logs:{job_id}", 86400 * 7)
    except Exception:
        pass


def log(message: str) -> None:
    formatted = f"[training-runner] {message}"
    print(formatted, flush=True)
    log_to_redis(formatted)


def metric_log(payload: dict) -> None:
    print(f"METRIC_JSON {json.dumps(payload, separators=(',', ':'))}", flush=True)


def warn(warnings: list[dict], code: str, message: str, **extra) -> None:
    warning = {"code": code, "message": message}
    warning.update(extra)
    warnings.append(warning)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def safe_json_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [safe_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): safe_json_value(item) for key, item in value.items()}
    return str(value)


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def parse_metric_events(stdout_text: str, warnings: list[dict]) -> tuple[list[dict], dict]:
    events: list[dict] = []
    metrics: dict = {}

    for line_number, line in enumerate(stdout_text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("METRIC_JSON:"):
            continue

        raw_payload = stripped.split("METRIC_JSON:", 1)[1].strip()
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            warn(
                warnings,
                "invalid_metric_json",
                "Invalid METRIC_JSON line was ignored.",
                line_number=line_number,
                error=str(exc),
            )
            continue

        if not isinstance(payload, dict):
            warn(
                warnings,
                "invalid_metric_json_shape",
                "METRIC_JSON payload must be a JSON object.",
                line_number=line_number,
            )
            continue

        normalized_payload = safe_json_value(payload)
        events.append({"line_number": line_number, "payload": normalized_payload})
        for key, value in normalized_payload.items():
            if is_number(value):
                metrics[str(key)] = value

    return events, metrics


def read_json_object(path: Path, label: str, warnings: list[dict]) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        warn(warnings, f"invalid_{label}_json", f"{label}.json could not be parsed and was ignored.", error=str(exc))
        return {}
    if not isinstance(payload, dict):
        warn(warnings, f"invalid_{label}_shape", f"{label}.json must contain a JSON object.")
        return {}
    return safe_json_value(payload)


def split_numeric_metrics(payload: dict, warnings: list[dict], source: str) -> dict:
    metrics = {}
    for key, value in payload.items():
        if is_number(value):
            metrics[str(key)] = value
        elif value is not None:
            warn(
                warnings,
                "non_numeric_metric_ignored",
                "Non-numeric metric value was ignored.",
                source=source,
                metric=str(key),
            )
    return metrics


def normalize_model_insights(payload: dict, default_kind: str = "") -> dict:
    if not isinstance(payload, dict):
        return {}

    kind = str(payload.get("kind") or default_kind or "feature_importance")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        feature_importance = payload.get("feature_importance")
        coefficients = payload.get("coefficients")
        if isinstance(feature_importance, dict):
            kind = "feature_importance"
            raw_items = [{"name": name, "value": value} for name, value in feature_importance.items()]
        elif isinstance(coefficients, dict):
            kind = "coefficients"
            raw_items = [{"name": name, "value": value} for name, value in coefficients.items()]
        else:
            raw_items = []

    items = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("feature") or "").strip()
        if not name:
            continue
        value = item.get("value", item.get("importance", item.get("coefficient")))
        if not is_number(value):
            continue
        normalized = {
            "name": name,
            "value": float(value),
            "abs_value": float(abs(value)),
        }
        class_name = item.get("class_name", item.get("class"))
        if class_name is not None:
            normalized["class_name"] = str(class_name)
        items.append(normalized)

    items = sorted(items, key=lambda entry: entry["abs_value"], reverse=True)[:MAX_MODEL_INSIGHT_ITEMS]
    for rank, item in enumerate(items, start=1):
        item["rank"] = rank

    if not items:
        return {}

    try:
        feature_count = int(payload.get("feature_count") or len(items))
    except (TypeError, ValueError):
        feature_count = len(items)

    return {
        "schema_version": "model-insights-v1",
        "kind": kind,
        "source": str(payload.get("source") or "training_artifact"),
        "feature_count": feature_count,
        "items": items,
    }


def read_model_insights(output_dir: Path, warnings: list[dict]) -> dict:
    for filename, default_kind in INSIGHTS_INPUT_FILES:
        path = output_dir / filename
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            warn(warnings, "invalid_model_insights_json", f"{filename} could not be parsed and was ignored.", error=str(exc))
            return {}
        insights = normalize_model_insights(payload, default_kind)
        if not insights:
            warn(warnings, "invalid_model_insights_shape", f"{filename} did not contain supported model insight items.")
            return {}
        return insights
    return {}


def artifact_kind(relative_path: Path) -> str:
    name = relative_path.name
    suffix = relative_path.suffix.lower()
    if name == "MLmodel" or suffix in MODEL_FILE_EXTENSIONS:
        return "model"
    if suffix in CHECKPOINT_EXTENSIONS:
        return "checkpoint"
    if suffix in METADATA_EXTENSIONS:
        return "metadata"
    if suffix == ".log":
        return "log"
    return "other"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_artifact_manifest(model_dir: Path) -> list[dict]:
    manifest = []
    root = model_dir.resolve()
    for item in sorted(model_dir.rglob("*")):
        if not item.is_file():
            continue
        resolved = item.resolve()
        if not resolved.is_relative_to(root):
            continue
        relative_path = item.relative_to(model_dir)
        manifest.append(
            {
                "path": relative_path.as_posix(),
                "size_bytes": item.stat().st_size,
                "sha256": sha256_file(item),
                "kind": artifact_kind(relative_path),
            }
        )
    return manifest


def write_metric_events(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True, default=str))
            handle.write("\n")


def log_to_mlflow(
    *,
    entry_point: str,
    model_version: str,
    training_job_id: str,
    tenant_id: str,
    status: str,
    metrics: dict,
    params: dict,
    model_dir: Path,
) -> None:
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "").strip()
    if not tracking_uri:
        return
    try:
        log(f"Connecting to MLflow Tracking Server at {tracking_uri}")
        mlflow.set_tracking_uri(tracking_uri)
        exp_name = os.environ.get("MLFLOW_EXPERIMENT_NAME", "").strip()
        if not exp_name:
            exp_name = f"tenant-{tenant_id}" if tenant_id else "default-tenant"
        artifact_root = os.environ.get("MLFLOW_ARTIFACT_ROOT", "").strip()
        if not artifact_root:
            raise RuntimeError("MLFLOW_ARTIFACT_ROOT is required for job-scoped MLflow artifacts")
        artifact_proxy_root = mlflow_proxy_artifact_uri(artifact_root)
        try:
            exp = mlflow.get_experiment_by_name(exp_name)
            if not exp:
                mlflow.create_experiment(exp_name, artifact_location=artifact_proxy_root)
        except Exception:
            pass
        mlflow.set_experiment(exp_name)

        run_name = f"job-{training_job_id}" if training_job_id else "training-job"
        with mlflow.start_run(run_name=run_name):
            if training_job_id:
                mlflow.set_tag("training_job_id", training_job_id)
            if tenant_id:
                mlflow.set_tag("tenant_id", tenant_id)
            if model_version:
                mlflow.set_tag("model_version", model_version)
            mlflow.set_tag("mlflow_artifact_root", artifact_root)
            mlflow.set_tag("entry_point", entry_point)
            mlflow.set_tag("status", status)

            if isinstance(params, dict):
                for k, v in params.items():
                    try:
                        mlflow.log_param(str(k)[:250], str(v)[:500])
                    except Exception:
                        pass

            if isinstance(metrics, dict):
                for k, v in metrics.items():
                    try:
                        if isinstance(v, (int, float)) and not isinstance(v, bool):
                            mlflow.log_metric(str(k)[:250], float(v))
                    except Exception:
                        pass

            if model_dir.exists():
                try:
                    mlflow.log_artifacts(str(model_dir), artifact_path="model")
                except Exception as exc:
                    log(f"Warning logging artifacts to MLflow: {exc}")
        log("Successfully logged training job parameters, metrics, and artifacts to MLflow")
    except Exception as exc:
        log(f"Warning: MLflow logging encountered an error: {exc}")


def mlflow_proxy_artifact_uri(artifact_root: str) -> str:
    """Map a job's durable S3 URI to MLflow's server-proxied artifact URI."""
    parsed = urlparse(artifact_root)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        raise RuntimeError(f"Invalid S3 URI for MLflow artifacts: {artifact_root!r}")
    return f"mlflow-artifacts:/{parsed.path.lstrip('/')}"


def write_mlops_bundle(
    *,
    entry_point: str,
    model_version: str,
    training_job_id: str,
    status: str,
    stdout_text: str,
    stderr_text: str,
) -> None:
    warnings: list[dict] = []
    mlops_dir = MODEL_DIR / MLOPS_DIR_NAME
    mlops_dir.mkdir(parents=True, exist_ok=True)

    metric_events, stdout_metrics = parse_metric_events(stdout_text, warnings)
    file_metrics_payload = read_json_object(OUTPUT_DIR / "metrics.json", "metrics", warnings)
    params_payload = read_json_object(OUTPUT_DIR / "params.json", "params", warnings)
    metrics = {**stdout_metrics, **split_numeric_metrics(file_metrics_payload, warnings, "metrics.json")}
    params = safe_json_value(params_payload)
    model_insights = read_model_insights(OUTPUT_DIR, warnings)

    (mlops_dir / "stdout.txt").write_text(stdout_text, encoding="utf-8")
    (mlops_dir / "stderr.txt").write_text(stderr_text, encoding="utf-8")
    write_metric_events(mlops_dir / "metric_events.jsonl", metric_events)
    write_json(mlops_dir / "metrics.json", metrics)
    write_json(mlops_dir / "params.json", params)
    if model_insights:
        write_json(mlops_dir / "model_insights.json", model_insights)
    write_json(mlops_dir / "warnings.json", warnings)

    manifest = build_artifact_manifest(MODEL_DIR)
    write_json(mlops_dir / "artifact_manifest.json", manifest)

    summary = {
        "runner_version": RUNNER_VERSION,
        "entry_point": entry_point,
        "model_version": model_version,
        "training_job_id": training_job_id,
        "status": status,
        "metrics": metrics,
        "params": params,
        "artifact_count": len(manifest),
        "warnings_count": len(warnings),
    }
    write_json(mlops_dir / "training_summary.json", summary)

    log_to_mlflow(
        entry_point=entry_point,
        model_version=model_version,
        training_job_id=training_job_id,
        tenant_id=os.environ.get("TENANT_ID", "").strip(),
        status=status,
        metrics=metrics,
        params=params,
        model_dir=MODEL_DIR,
    )


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def validate_presigned_url(uri: str) -> None:
    parsed = urlparse(uri)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("Training runner requires a presigned HTTP(S) URL.")


def download_presigned_url(uri: str, destination: Path) -> None:
    validate_presigned_url(uri)
    destination.parent.mkdir(parents=True, exist_ok=True)
    log(f"Downloading presigned URL to {destination}")
    with requests.get(uri, stream=True, timeout=300) as response:
        response.raise_for_status()
        with open(destination, "wb") as out_file:
            for chunk in response.iter_content(chunk_size=8192):
                out_file.write(chunk)


def upload_presigned_url(source: Path, uri: str) -> None:
    validate_presigned_url(uri)
    log(f"Uploading {source} via presigned PUT URL")

    with open(source, "rb") as handle:
        response = requests.put(uri, data=handle, timeout=300)
    if response.status_code not in (200, 201, 204):
        raise RuntimeError(
            f"Presigned PUT upload failed with HTTP status {response.status_code}: {response.text}"
        )


def request_output_upload_url(endpoint: str, capability: str) -> str:
    validate_presigned_url(endpoint)
    if not capability:
        raise RuntimeError("Missing output upload capability.")

    response = requests.post(endpoint, headers={"Authorization": f"Bearer {capability}"}, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"Output upload URL request failed with HTTP status {response.status_code}.")
    payload = response.json()
    upload_url = str(payload.get("upload_url", "")).strip()
    validate_presigned_url(upload_url)
    return upload_url


def safe_extract_zip(zip_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        destination_root = destination.resolve()
        for member in archive.infolist():
            member_path = (destination / member.filename).resolve()
            is_symlink = (member.external_attr >> 16) & 0o170000 == 0o120000
            if not member_path.is_relative_to(destination_root) or is_symlink:
                raise RuntimeError("Source zip contains an unsafe path.")
        archive.extractall(destination)


def install_requirements(requirements_path: Path) -> None:
    if not requirements_path.exists():
        return
    log("Installing requirements.txt")
    res = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(requirements_path)],
        cwd=str(SOURCE_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    if res.stdout:
        for line in res.stdout.splitlines():
            print(line, flush=True)
            log_to_redis(line)
    if res.stderr:
        for line in res.stderr.splitlines():
            print(line, file=sys.stderr, flush=True)
            log_to_redis(line)
    if res.returncode != 0:
        raise RuntimeError(f"pip install -r requirements.txt failed with exit code {res.returncode}")


def _read_int_file(path: str) -> int | None:
    try:
        value = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if value in {"", "max"}:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _read_cgroup_cpu_usage_seconds() -> float | None:
    cpu_stat = Path("/sys/fs/cgroup/cpu.stat")
    if cpu_stat.exists():
        try:
            for line in cpu_stat.read_text(encoding="utf-8").splitlines():
                key, value = line.split(maxsplit=1)
                if key == "usage_usec":
                    return int(value) / 1_000_000
        except (OSError, ValueError):
            return None

    usage_ns = _read_int_file("/sys/fs/cgroup/cpuacct/cpuacct.usage")
    if usage_ns is not None:
        return usage_ns / 1_000_000_000
    return None


def _read_cgroup_cpu_limit() -> float:
    cpu_max = Path("/sys/fs/cgroup/cpu.max")
    if cpu_max.exists():
        try:
            quota_raw, period_raw = cpu_max.read_text(encoding="utf-8").strip().split(maxsplit=1)
            if quota_raw != "max":
                quota = int(quota_raw)
                period = int(period_raw)
                if quota > 0 and period > 0:
                    return max(quota / period, 0.001)
        except (OSError, ValueError):
            pass

    quota = _read_int_file("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
    period = _read_int_file("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
    if quota and period and quota > 0 and period > 0:
        return max(quota / period, 0.001)
    return float(os.cpu_count() or 1)


def _read_cgroup_memory() -> tuple[float | None, float | None, float | None]:
    used = _read_int_file("/sys/fs/cgroup/memory.current")
    limit = _read_int_file("/sys/fs/cgroup/memory.max")

    if used is None:
        used = _read_int_file("/sys/fs/cgroup/memory/memory.usage_in_bytes")
    if limit is None:
        limit = _read_int_file("/sys/fs/cgroup/memory/memory.limit_in_bytes")

    if limit and limit > 8 * 1024 * 1024 * 1024 * 1024:
        limit = None

    used_mb = round(used / 1024 / 1024, 2) if used is not None else None
    limit_mb = round(limit / 1024 / 1024, 2) if limit else None
    percent = round((used / limit) * 100, 2) if used is not None and limit else None
    return used_mb, limit_mb, percent


def _read_gpu_metrics() -> dict:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {
            "gpu_available": False,
            "gpu_percent": None,
            "gpu_memory_used_mb": None,
            "gpu_memory_total_mb": None,
            "gpu_memory_percent": None,
        }

    if result.returncode != 0 or not result.stdout.strip():
        return {
            "gpu_available": False,
            "gpu_percent": None,
            "gpu_memory_used_mb": None,
            "gpu_memory_total_mb": None,
            "gpu_memory_percent": None,
        }

    gpu_rows = []
    for line in result.stdout.strip().splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 3:
            continue
        try:
            gpu_percent, memory_used, memory_total = (float(parts[0]), float(parts[1]), float(parts[2]))
        except ValueError:
            continue
        gpu_rows.append((gpu_percent, memory_used, memory_total))

    if not gpu_rows:
        return {
            "gpu_available": False,
            "gpu_percent": None,
            "gpu_memory_used_mb": None,
            "gpu_memory_total_mb": None,
            "gpu_memory_percent": None,
        }

    gpu_percent = max(row[0] for row in gpu_rows)
    memory_used = sum(row[1] for row in gpu_rows)
    memory_total = sum(row[2] for row in gpu_rows)
    return {
        "gpu_available": True,
        "gpu_percent": round(gpu_percent, 2),
        "gpu_memory_used_mb": round(memory_used, 2),
        "gpu_memory_total_mb": round(memory_total, 2),
        "gpu_memory_percent": round((memory_used / memory_total) * 100, 2) if memory_total else None,
    }


def start_metric_emitter(stop_event: threading.Event, interval_seconds: int = 5) -> threading.Thread:
    def emit_loop() -> None:
        cpu_limit = _read_cgroup_cpu_limit()
        previous_usage = _read_cgroup_cpu_usage_seconds()
        previous_time = time.monotonic()

        while not stop_event.is_set():
            now = time.monotonic()
            current_usage = _read_cgroup_cpu_usage_seconds()
            cpu_percent = None
            if previous_usage is not None and current_usage is not None and now > previous_time:
                cpu_percent = round(((current_usage - previous_usage) / (now - previous_time) / cpu_limit) * 100, 2)
                cpu_percent = max(0.0, min(cpu_percent, 100.0))
            previous_usage = current_usage
            previous_time = now

            memory_used_mb, memory_limit_mb, memory_percent = _read_cgroup_memory()
            metric_log(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "cpu_percent": cpu_percent,
                    "cpu_limit_cores": round(cpu_limit, 2),
                    "memory_used_mb": memory_used_mb,
                    "memory_limit_mb": memory_limit_mb,
                    "memory_percent": memory_percent,
                    **_read_gpu_metrics(),
                }
            )
            stop_event.wait(interval_seconds)

    thread = threading.Thread(target=emit_loop, name="training-metrics", daemon=True)
    thread.start()
    return thread


def run_training(entry_point: str, model_version: str) -> subprocess.CompletedProcess:
    entry_point_path = SOURCE_DIR / entry_point
    if not entry_point_path.exists() or not entry_point_path.is_file():
        raise RuntimeError(f"Source zip must contain entry point: {entry_point}")

    env = {
        name: os.environ[name]
        for name in ("HOME", "LANG", "LC_ALL", "PATH", "PYTHONPATH", "TZ")
        if os.environ.get(name)
    }
    env.update(
        {
            "SM_CHANNEL_TRAIN": str(INPUT_TRAIN_DIR),
            "SM_MODEL_DIR": str(MODEL_DIR),
            "SM_OUTPUT_DIR": str(OUTPUT_DIR),
            "MODEL_VERSION": model_version,
        }
    )

    log(f"Running training entry point: {entry_point}")
    stop_metrics = threading.Event()
    start_metric_emitter(stop_metrics)
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    def stream_lines(stream, output, lines):
        if stream is None:
            return
        for line in iter(stream.readline, ""):
            print(line, end="", file=output, flush=True)
            log_to_redis(line.rstrip("\n"))
            lines.append(line)

    try:
        process = subprocess.Popen(
            [sys.executable, str(entry_point_path)],
            cwd=str(SOURCE_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        stdout_thread = threading.Thread(
            target=stream_lines,
            args=(process.stdout, sys.stdout, stdout_lines),
            name="training-stdout",
        )
        stderr_thread = threading.Thread(
            target=stream_lines,
            args=(process.stderr, sys.stderr, stderr_lines),
            name="training-stderr",
        )
        stdout_thread.start()
        stderr_thread.start()
        process.wait()
        stdout_thread.join()
        stderr_thread.join()
    finally:
        stop_metrics.set()
    return subprocess.CompletedProcess(
        args=[sys.executable, str(entry_point_path)],
        returncode=process.returncode,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
    )


def create_model_archive(archive_path: Path) -> None:
    model_files = [
        item
        for item in MODEL_DIR.rglob("*")
        if item.is_file() and MLOPS_DIR_NAME not in item.relative_to(MODEL_DIR).parts
    ]
    if not model_files:
        raise RuntimeError("Training completed but SM_MODEL_DIR does not contain any model files.")

    log(f"Packaging {len(model_files)} model file(s) into model.tar.gz")
    with tarfile.open(archive_path, "w:gz") as archive:
        for item in MODEL_DIR.rglob("*"):
            if item.is_file():
                archive.add(item, arcname=item.relative_to(MODEL_DIR))


def main() -> None:
    source_uri = require_env("S3_SOURCE_URI")
    training_data_uri = require_env("S3_TRAINING_DATA_URI")
    output_upload_endpoint = require_env("S3_OUTPUT_UPLOAD_URL")
    output_upload_capability = require_env("S3_OUTPUT_UPLOAD_CAPABILITY")
    entry_point = os.environ.get("ENTRY_POINT", "train.py").strip() or "train.py"
    model_version = os.environ.get("MODEL_VERSION", "").strip()
    training_job_id = os.environ.get("TRAINING_JOB_ID", "").strip()
    requirements_uri = os.environ.get("S3_REQUIREMENTS_URI", "").strip()

    log("Preparing workspace")
    if WORKSPACE.exists():
        shutil.rmtree(WORKSPACE)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    INPUT_TRAIN_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    source_zip_path = WORKSPACE / "source.zip"
    train_csv_path = INPUT_TRAIN_DIR / "train.csv"
    requirements_path = SOURCE_DIR / "requirements.txt"
    model_archive_path = OUTPUT_DIR / "model.tar.gz"

    download_presigned_url(source_uri, source_zip_path)
    download_presigned_url(training_data_uri, train_csv_path)
    if requirements_uri:
        download_presigned_url(requirements_uri, requirements_path)

    log("Extracting source zip")
    safe_extract_zip(source_zip_path, SOURCE_DIR)

    requirements_text = os.environ.get("REQUIREMENTS_TEXT", "").strip()
    if requirements_text:
        try:
            decoded = base64.b64decode(requirements_text.encode("utf-8")).decode("utf-8")
            if any(c.isalpha() for c in decoded):
                requirements_text = decoded
        except Exception:
            pass
        if "\n" not in requirements_text and " " in requirements_text:
            requirements_text = "\n".join(requirements_text.split())
        log("Writing requirements.txt from REQUIREMENTS_TEXT env var")
        requirements_path.write_text(requirements_text, encoding="utf-8")

    install_requirements(requirements_path)
    result = run_training(entry_point, model_version)
    training_status = "succeeded" if result.returncode == 0 else "failed"
    write_mlops_bundle(
        entry_point=entry_point,
        model_version=model_version,
        training_job_id=training_job_id,
        status=training_status,
        stdout_text=result.stdout or "",
        stderr_text=result.stderr or "",
    )
    if result.returncode != 0:
        raise RuntimeError(f"Training entry point failed with exit code {result.returncode}")
    create_model_archive(model_archive_path)
    upload_presigned_url(
        model_archive_path,
        request_output_upload_url(output_upload_endpoint, output_upload_capability),
    )
    log("Training job completed successfully")


if __name__ == "__main__":
    main()
