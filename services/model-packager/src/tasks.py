import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import docker
import mlflow.pyfunc
import redis
import requests
import yaml
from src import config, image_build, io
from src.core import (
    build_preview_tree,
    load_model,
    make_zip,
    parse_requirements,
    save_mlflow_model,
)
from src.image_build import serving_base_image, write_build_context
from src.logging_utils import (
    RuntimeLog,
    bind_context,
    configure,
    get_logger,
    log_event,
    reset_context,
    sanitize,
)
from src.security import (
    validate_model_package_security,
    validate_no_dangerous_binaries,
    validate_safe_requirements,
)

logger = get_logger("model-packager")
runtime_log = RuntimeLog(logger)


class RedisLogHandler(logging.Handler):
    def __init__(self, redis_url: str, build_id: str):
        super().__init__()
        self.redis_client = redis.from_url(redis_url)
        self.log_key = f"build_logs:{build_id}"
        self.redis_client.delete(self.log_key)

    def write(self, message: str) -> bool:
        try:
            self.redis_client.rpush(self.log_key, sanitize(message))
            self.redis_client.expire(self.log_key, 3600)
            return True
        except Exception:
            # RuntimeLog emits a sanitized container fallback on delivery failure.
            return False

    def emit(self, record):
        try:
            self.write(self.format(record))
        except Exception:
            # Never use handleError: it dumps the unsanitized record to stderr.
            pass


def download_presigned_file(download_url: str, destination: Path) -> None:
    io.download_presigned_file(download_url, destination, requests, runtime_log.detail)


def upload_presigned_file(upload_url: str, source: Path) -> None:
    io.upload_presigned_file(upload_url, source, requests, runtime_log.detail)


def safe_extract_tar(archive_path: Path, destination: Path) -> None:
    io.safe_extract_tar(archive_path, destination)


def safe_extract_zip(archive_path: Path, destination: Path) -> None:
    io.safe_extract_zip(archive_path, destination)


def webhook_headers() -> dict[str, str]:
    secret = os.environ.get("CONTROL_PLANE_WEBHOOK_SECRET", "").strip()
    return {"X-Control-Plane-Secret": secret} if secret else {}


def post_webhook(webhook_url: str, payload: dict) -> None:
    io.post_webhook(webhook_url, payload, requests, webhook_headers())


def configured_image_reference(build_id: str = "") -> str:
    return config.image_reference(os.environ, build_id)


def built_image_metadata() -> dict[str, str]:
    image_uri = configured_image_reference()
    try:
        image = docker.from_env().images.get(image_uri)
        repo_digests = image.attrs.get("RepoDigests") or []
        digest = repo_digests[0].split("@", 1)[1] if repo_digests else image.attrs.get("Id", "")
    except Exception:
        digest = ""
    return {"image_uri": image_uri, "image_digest": digest}


def build_custom_image(workspace: Path, build_id: str, tenant_id: str, requirements_text: str) -> None:
    image_build.build_image(
        workspace=workspace,
        build_id=build_id,
        requirements_text=requirements_text,
        serving_image="machine-learning-serving",
        image_label="",
        docker_module=docker,
        environment=os.environ,
        image_reference=configured_image_reference,
        detail=runtime_log.detail,
    )


def build_bento_image(workspace: Path, build_id: str, tenant_id: str, requirements_text: str) -> None:
    image_build.build_image(
        workspace=workspace,
        build_id=build_id,
        requirements_text=requirements_text,
        serving_image="deep-learning-serving",
        image_label="BentoML ",
        docker_module=docker,
        environment=os.environ,
        image_reference=configured_image_reference,
        detail=runtime_log.detail,
    )


def parse_conda_pip_requirements(conda_file: Path) -> list[str]:
    with conda_file.open("r", encoding="utf-8") as handle:
        conda_env = yaml.safe_load(handle) or {}

    pip_requirements = []
    for dep in conda_env.get("dependencies", []):
        if isinstance(dep, dict) and "pip" in dep:
            pip_requirements.extend(dep["pip"])
    return pip_requirements


def run_build_task(build_id: str, webhook_url: str) -> None:
    flavor = os.environ.get("FLAVOR", "").lower()
    requirements_text = os.environ.get("REQUIREMENTS_TEXT", "")
    source_download_url = os.environ.get("SOURCE_DOWNLOAD_URL", "")
    source_artifact_name = os.environ.get("SOURCE_ARTIFACT_NAME", "")
    source_type = os.environ.get("SOURCE_TYPE", "manual_upload")
    output_upload_url = os.environ.get("OUTPUT_UPLOAD_URL", "")
    label_mapping_download_url = os.environ.get("LABEL_MAPPING_DOWNLOAD_URL", "")
    label_mapping_filename = os.environ.get("LABEL_MAPPING_FILENAME", "")
    tenant_id = os.environ.get("TENANT_ID", "unknown")

    if source_type == "training_job":
        if not all([flavor, source_download_url, source_artifact_name, output_upload_url]):
            raise ValueError("Missing presigned URLs for training artifact build.")
    elif not all([flavor, source_download_url, source_artifact_name, output_upload_url]):
        raise ValueError("Missing required environment variables for build.")

    workspace_dir = os.environ.get("BUILD_WORKSPACE_DIR")
    if workspace_dir:
        workspace = Path(workspace_dir)
        workspace.mkdir(parents=True, exist_ok=True)
        runtime_log.detail(f"Using shared workspace directory: {workspace}")
    else:
        workspace = Path(tempfile.mkdtemp(prefix=f"build-{build_id}-"))
    try:
        artifact_name = Path(source_artifact_name).name
        artifact_path = workspace / artifact_name
        download_presigned_file(source_download_url, artifact_path)
        validate_model_package_security(artifact_path)
        if requirements_text.strip():
            validate_safe_requirements(requirements_text)

        runtime_log.detail(f"Loading {flavor} model...")
        model = load_model(artifact_path, flavor)
        package_name = "model"
        package_dir = workspace / package_name
        requirements = parse_requirements(requirements_text)

        runtime_log.detail("Saving MLflow model format...")
        save_mlflow_model(model, flavor, package_dir, requirements)

        if requirements_text.strip():
            (package_dir / "requirements.txt").write_text(requirements_text.strip() + "\n", encoding="utf-8")

        schema_url = os.environ.get("INPUT_SCHEMA_DOWNLOAD_URL", "")
        if schema_url:
            download_presigned_file(schema_url, package_dir / "input_schema.json")
        if label_mapping_download_url:
            mapping_path = package_dir / Path(label_mapping_filename or "label-mapping.json").name
            download_presigned_file(label_mapping_download_url, mapping_path)
        preview_tree = build_preview_tree(package_dir)
        manifest = {
            "flavor": flavor,
            "source_type": source_type,
            "source_artifact": artifact_name,
            "package_root": package_name,
            "requirements_count": len(requirements or []),
        }

        zip_path = workspace / "model-package.zip"
        runtime_log.detail("Compressing package to zip...")
        make_zip(package_dir, zip_path)

        upload_presigned_file(output_upload_url, zip_path)

        if os.environ.get("BUILD_ENGINE", "").lower() == "kaniko":
            runtime_log.detail("Kaniko build engine detected. Preparing build context without Docker daemon...")
            harbor_url = os.environ.get("HARBOR_REGISTRY_URL", "").strip().rstrip("/")
            if flavor in ["pytorch", "tensorflow", "keras"]:
                runtime_log.detail("Detected Deep Learning flavor. Generating BentoML Dockerfile...")
                serving_image = "deep-learning-serving"
            else:
                runtime_log.detail("Generating custom lightweight Dockerfile...")
                serving_image = "machine-learning-serving"
            write_build_context(
                workspace, serving_base_image(serving_image, harbor_url), requirements_text, runtime_log.detail
            )

            payload = {
                "build_id": build_id,
                "status": "success",
                "package_manifest": manifest,
                "package_preview_tree": preview_tree,
                "task_type": "BUILD",
                "requirements_snapshot": requirements_text,
            }
            (workspace / "webhook_payload.json").write_text(
                json.dumps(io.finite_json(payload), allow_nan=False), encoding="utf-8"
            )
            runtime_log.protocol("Build context prepared successfully for Kaniko! BUILD_PREPARE_SUCCESS")
            return
        elif flavor in ["pytorch", "tensorflow", "keras"]:
            runtime_log.detail("Detected Deep Learning flavor. Building BentoML container image...")
            build_bento_image(workspace, build_id, tenant_id, requirements_text)
        else:
            runtime_log.detail("Building custom lightweight Docker image...")
            build_custom_image(workspace, build_id, tenant_id, requirements_text)
        runtime_log.detail("Build completed successfully!")

        post_webhook(
            webhook_url,
            {
                "build_id": build_id,
                "status": "success",
                "package_manifest": manifest,
                "package_preview_tree": preview_tree,
                "task_type": "BUILD",
                **built_image_metadata(),
            },
        )
        runtime_log.protocol("BUILD_EOF_SUCCESS")
    finally:
        if not os.environ.get("BUILD_WORKSPACE_DIR"):
            shutil.rmtree(workspace, ignore_errors=True)


def run_test_zip_task(build_id: str, webhook_url: str) -> None:
    source_download_url = os.environ.get("SOURCE_DOWNLOAD_URL", "")
    source_artifact_name = os.environ.get("SOURCE_ARTIFACT_NAME", "")
    output_upload_url = os.environ.get("OUTPUT_UPLOAD_URL", "")
    flavor = os.environ.get("FLAVOR", "").lower()
    tenant_id = os.environ.get("TENANT_ID", "unknown")
    if not all([source_download_url, source_artifact_name]):
        raise ValueError("Missing presigned download URL for test.")
    if not output_upload_url:
        raise ValueError("Missing presigned package upload URL for test.")

    workspace_dir = os.environ.get("BUILD_WORKSPACE_DIR")
    if workspace_dir:
        workspace = Path(workspace_dir)
        workspace.mkdir(parents=True, exist_ok=True)
        runtime_log.detail(f"Using shared workspace directory: {workspace}")
    else:
        workspace = Path(tempfile.mkdtemp(prefix=f"test-{build_id}-"))
    try:
        artifact_name = Path(source_artifact_name).name
        zip_path = workspace / artifact_name

        download_presigned_file(source_download_url, zip_path)
        runtime_log.detail("Scanning model package security...")
        validate_model_package_security(zip_path)

        extract_dir = workspace / "extracted"
        runtime_log.detail("Extracting ZIP archive safely...")
        safe_extract_zip(zip_path, extract_dir)
        validate_no_dangerous_binaries(extract_dir)

        mlmodel_paths = list(extract_dir.rglob("MLmodel"))
        if not mlmodel_paths:
            raise ValueError("No MLmodel file found in the ZIP archive.")

        package_dir = mlmodel_paths[0].parent
        runtime_log.detail(f"Found MLmodel at {package_dir.relative_to(extract_dir)}")
        shutil.copytree(package_dir, workspace / "model", dirs_exist_ok=True)

        requirements_text = ""
        req_file = package_dir / "requirements.txt"
        conda_file = package_dir / "conda.yaml"
        if req_file.exists():
            requirements_text = req_file.read_text(encoding="utf-8").strip()
            runtime_log.detail("Found requirements.txt.")
        elif conda_file.exists():
            pip_requirements = parse_conda_pip_requirements(conda_file)
            if pip_requirements:
                requirements_text = "\n".join(pip_requirements)
                runtime_log.detail("Extracted pip requirements from conda.yaml.")
        else:
            runtime_log.detail("No requirements.txt or conda.yaml found. Proceeding with default environment.")

        if requirements_text.strip():
            validate_safe_requirements(requirements_text)
            runtime_log.detail("Installing package requirements for validation...")
            temp_req = workspace / "validation-requirements.txt"
            temp_req.write_text(requirements_text + "\n", encoding="utf-8")
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", str(temp_req)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as exc:
                for output in (exc.stdout, exc.stderr):
                    for line in (output or "").splitlines():
                        runtime_log.detail(line)
                raise
            for output in (result.stdout, result.stderr):
                for line in (output or "").splitlines():
                    runtime_log.detail(line)

        runtime_log.detail("Validating model load via mlflow.pyfunc...")

        mlflow.pyfunc.load_model(str(package_dir))
        runtime_log.detail("Model loaded successfully!")

        # Registration copies the package from OUTPUT_UPLOAD_URL's object key.
        # Persist validated ZIPs just as the raw-model BUILD path does, before
        # declaring the build context ready or sending a success callback.
        upload_presigned_file(output_upload_url, zip_path)

        preview_tree = build_preview_tree(extract_dir)
        manifest = {
            "flavor": flavor,
            "source_type": "manual_upload",
            "source_artifact": artifact_name,
            "package_root": package_dir.name,
        }

        runtime_log.detail("Building custom Docker image...")
        if os.environ.get("BUILD_ENGINE", "").lower() == "kaniko":
            runtime_log.detail("Kaniko build engine detected. Preparing build context for TEST_ZIP...")
            harbor_url = os.environ.get("HARBOR_REGISTRY_URL", "").strip().rstrip("/")
            is_deep_learning = flavor in ["pytorch", "tensorflow", "keras"]
            write_build_context(
                workspace,
                serving_base_image(
                    "deep-learning-serving" if is_deep_learning else "machine-learning-serving", harbor_url
                ),
                requirements_text,
                runtime_log.detail,
            )
            payload = {
                "build_id": build_id,
                "status": "success",
                "package_manifest": manifest,
                "package_preview_tree": preview_tree,
                "task_type": "TEST_ZIP",
                "requirements_snapshot": requirements_text,
            }
            (workspace / "webhook_payload.json").write_text(
                json.dumps(io.finite_json(payload), allow_nan=False), encoding="utf-8"
            )
            runtime_log.protocol("TEST_ZIP context prepared successfully for Kaniko! BUILD_PREPARE_SUCCESS")
            return
        else:
            if flavor in ["pytorch", "tensorflow", "keras"]:
                build_bento_image(workspace, build_id, tenant_id, requirements_text)
            else:
                build_custom_image(workspace, build_id, tenant_id, requirements_text)
        runtime_log.detail("Test and build completed successfully!")

        post_webhook(
            webhook_url,
            {
                "build_id": build_id,
                "status": "success",
                "package_manifest": manifest,
                "package_preview_tree": preview_tree,
                "task_type": "TEST_ZIP",
                **built_image_metadata(),
            },
        )
        runtime_log.protocol("BUILD_EOF_SUCCESS")
    finally:
        if not os.environ.get("BUILD_WORKSPACE_DIR"):
            shutil.rmtree(workspace, ignore_errors=True)


def run_notify_task(workspace_dir: str, webhook_url: str) -> None:
    workspace = Path(workspace_dir)
    payload_file = workspace / "webhook_payload.json"
    if not payload_file.exists():
        raise FileNotFoundError(f"Webhook payload not found at {payload_file}")
    # Contexts prepared by an older packager may still hold NaN/Infinity tokens.
    payload = io.finite_json(json.loads(payload_file.read_text(encoding="utf-8")))
    image_uri = os.environ.get("IMAGE_URI", "").strip()
    digest_file = workspace / "image-digest"
    if image_uri:
        payload["image_uri"] = image_uri
    if digest_file.exists():
        payload["image_digest"] = digest_file.read_text(encoding="utf-8").strip()
    runtime_log.detail(f"Sending post-build notification for build {payload.get('build_id')}...")
    post_webhook(webhook_url, payload)
    runtime_log.protocol("NOTIFY_EOF_SUCCESS")


def setup_logger(build_id: str):
    global runtime_log
    configure("model-packager")
    writer = None
    if os.environ.get("LOG_STORAGE_BACKEND", "").strip().lower() != "loki":
        redis_url = os.environ.get("REDIS_URL", "redis://redis-cache:6379/0")
        if redis_url and build_id:
            try:
                writer = RedisLogHandler(redis_url, build_id).write
            except Exception as exc:
                log_event(
                    logger,
                    logging.WARNING,
                    "runtime_log_unavailable",
                    "Could not connect to Redis for build log streaming",
                    reason=sanitize(str(exc)),
                )
    runtime_log = RuntimeLog(logger, writer=writer)
    return logger


def main():
    started = time.monotonic()
    build_id = os.environ.get("BUILD_ID")
    setup_logger(build_id or "")
    if not build_id:
        runtime_log.event(
            logging.ERROR,
            "build_execution_failed",
            "Missing BUILD_ID",
            duration_ms=round((time.monotonic() - started) * 1000, 3),
        )
        sys.exit(1)

    webhook_url = os.environ.get("CONTROL_PLANE_WEBHOOK_URL")

    task_type = os.environ.get("TASK_TYPE", "BUILD")
    tokens = bind_context(
        build_id=build_id,
        project_id=os.environ.get("PROJECT_ID"),
        tenant_id=os.environ.get("TENANT_ID"),
        operation=task_type,
    )
    try:
        runtime_log.event(
            logging.INFO,
            "build_execution_started",
            f"Starting {task_type} process",
            duration_ms=0,
        )

        if task_type == "NOTIFY_BUILD":
            workspace_dir = os.environ.get("BUILD_WORKSPACE_DIR", "/workspace")
            run_notify_task(workspace_dir, webhook_url)
        elif task_type == "TEST_ZIP":
            run_test_zip_task(build_id, webhook_url)
        else:
            run_build_task(build_id, webhook_url)
        if task_type == "NOTIFY_BUILD":
            runtime_log.event(
                logging.INFO,
                "build.notification.completed",
                "Build notification execution completed",
                duration_ms=round((time.monotonic() - started) * 1000, 3),
            )
        elif os.environ.get("BUILD_ENGINE", "").lower() == "kaniko":
            runtime_log.event(
                logging.INFO,
                "build.preparation.completed",
                "Build context preparation completed",
                duration_ms=round((time.monotonic() - started) * 1000, 3),
            )
        else:
            runtime_log.event(
                logging.INFO,
                "build_execution_succeeded",
                "Build runner execution completed",
                duration_ms=round((time.monotonic() - started) * 1000, 3),
            )
    except Exception as exc:
        runtime_log.event(
            logging.ERROR,
            "build_execution_failed",
            "Build runner execution failed",
            reason=sanitize(str(exc)),
            exc_info=True,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
        )
        try:
            if webhook_headers():
                post_webhook(
                    webhook_url,
                    {
                        "build_id": build_id,
                        "status": "error",
                        "error_message": sanitize(str(exc)),
                    },
                )
            else:
                # Steps that run user code hold no callback secret; the workflow's exit
                # handler reports the failure instead.
                runtime_log.detail(
                    "No callback credential in this step; the workflow exit handler reports the failure."
                )
        except Exception as webhook_exc:
            runtime_log.event(
                logging.ERROR,
                "build_failure_callback_failed",
                "Failed to notify Control Plane failure webhook",
                reason=sanitize(str(webhook_exc)),
            )

        runtime_log.protocol("BUILD_EOF_ERROR")
        sys.exit(1)
    finally:
        reset_context(tokens)
