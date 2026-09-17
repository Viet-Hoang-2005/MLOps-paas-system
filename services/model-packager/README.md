# Model Packager — Build Job Container

Model Packager là container thực thi quá trình **đóng gói mô hình** — biến một artifact tải lên (ZIP chứa MLflow model) thành Docker Image hoàn chỉnh có thể chạy được trong K3s. Service này được gọi bởi **build pipeline** (Argo Workflow hoặc Docker SDK), không expose HTTP API.

---

## Vai Trò

- **Chuẩn hóa Artifact**: Tải model artifact từ S3 (hoặc MLflow artifact URI), giải nén, tìm file model (`.pkl`, `.joblib`, `.xgb`), chuẩn hóa sang MLflow Pyfunc format.
- **Sinh Dockerfile**: Tự động chọn Base Image phù hợp với `flavor`:
  - `pytorch` / `keras` / `tensorflow` → dùng `deep-learning-serving` base image với BentoML.
  - `sklearn` / `scikit-learn` / `xgboost` → dùng `machine-learning-serving` base image với FastAPI.
- **Build Docker Image**:
  - **Local** (`BUILD_ENGINE=docker`): Dùng Docker SDK (`docker-py`) để build vào Docker Desktop; chỉ push khi repository đích thuộc Harbor.
  - **Production K3s** (`BUILD_ENGINE=kaniko`): Sinh `Dockerfile` + `requirements.txt` vào `/workspace` (emptyDir volume) để Kaniko executor (step tiếp theo trong Argo Workflow) thực hiện build rootless.
- **Log Streaming**: Ghi log build vào Redis (`build_logs:{build_id}`) để Frontend HTTP Polling hiển thị.
- **Webhook Callback** (`TASK_TYPE=NOTIFY_BUILD`): Sau khi Kaniko build xong, đọc `webhook_payload.json` từ `/workspace` và gửi POST về Control Plane thông báo trạng thái.

---

## Luồng Argo 3-Step (Production K3s)

```
Step 1: model-packager (TASK_TYPE=BUILD, BUILD_ENGINE=kaniko)
  → Tải artifact từ S3
  → Chuẩn hóa MLflow format
  → Sinh Dockerfile + requirements.txt → /workspace/
  → Ghi webhook_payload.json → /workspace/

Step 2: kaniko-executor
  → Đọc /workspace/Dockerfile
  → Build rootless (không Docker socket)
  → Push image → Harbor Registry

Step 3: model-packager (TASK_TYPE=NOTIFY_BUILD)
  → Đọc /workspace/webhook_payload.json
  → POST webhook → Control Plane (build success/error)
```

---

## Cấu Trúc Thư Mục

```
src/
├── main.py         # Process entrypoint and exit-code handling
├── tasks.py        # BUILD, TEST_ZIP and NOTIFY_BUILD workflows
├── config.py       # Environment-backed image naming
├── io.py           # Presigned transfer, safe extraction and webhook delivery
├── image_build.py  # Docker build context and image publication
└── core.py         # Model loading, MLflow packaging and preview utilities
```

---

## Công nghệ

| Thành phần | Công nghệ |
|---|---|
| Model Loading | `mlflow.pyfunc`, `joblib`, `xgboost` |
| Build (Local) | `docker-py` SDK |
| Build (Production) | Kaniko (rootless, sinh Dockerfile context vào emptyDir) |
| Storage | Presigned S3 HTTP URLs via `requests` |
| Log Buffer | `redis` (key: `build_logs:{build_id}`, TTL 1h) |

---

## Biến Môi Trường

| Biến | Mô tả |
|---|---|
| `TASK_TYPE` | `BUILD` (chuẩn bị + build) hoặc `NOTIFY_BUILD` (gửi webhook sau Kaniko) |
| `BUILD_ENGINE` | `docker` (local) hoặc `kaniko` (production) |
| `BUILD_WORKSPACE_DIR` | Đường dẫn shared volume với Kaniko (mặc định: `/workspace`) |
| `BUILD_ID` | UUID của Build; correlation ID cho log, callback và tag tạm |
| `PROJECT_ID` | UUID của ModelProject; dùng để xác định image repository |
| `IMAGE_REPOSITORY` | Repository chuẩn hóa, ví dụ `image-{project_uuid}` |
| `IMAGE_TAG` | Tag tạm, ví dụ `build-{build_uuid}` |
| `TENANT_ID` | Tenant sở hữu model |
| `FLAVOR` | Loại model (`bento` hoặc standard) |
| `SOURCE_DOWNLOAD_URL` | Presigned GET URL cho artifact model hoặc training archive |
| `LABEL_MAPPING_DOWNLOAD_URL` | Presigned GET URL cho label mapping (optional) |
| `OUTPUT_UPLOAD_URL` | Presigned PUT URL để tải model package lên S3 |
| `HARBOR_REGISTRY_URL`, `HARBOR_USERNAME`, `HARBOR_PASSWORD` | Harbor config |
| `CONTROL_PLANE_WEBHOOK_URL` | URL callback kết quả build |
| `CONTROL_PLANE_WEBHOOK_SECRET` | HMAC secret xác thực webhook |
| `REDIS_URL` | Redis để stream build logs |
