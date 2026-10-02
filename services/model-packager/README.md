# Model Packager — Đóng Gói Mô Hình & Xây Dựng Container Image (Build Engine)

Thư mục `services/model-packager/` chứa mã nguồn của **Model Packager Service**, một worker container độc lập thực thi tác vụ đóng gói mô hình học máy (Packaging & Container Image Build). Dịch vụ chuyển hóa các artifact mô hình thô (Pickle, PyTorch, TensorFlow hoặc MLflow bundle) thành một OCI Container Image hoàn chỉnh, sẵn sàng triển khai phục vụ trên cụm Kubernetes hoặc Docker Engine.

---

## 1. Giới thiệu

### 1.1. Vai trò trong hệ thống

Trong nền tảng MLOps PaaS, Model Packager là thành phần thực thi của tiến trình **Build Pipeline** được kích hoạt bởi Control Plane (thông qua Docker SDK ở môi trường local hoặc Argo Workflows trên Kubernetes):

1. **Chuẩn hóa Artifact sang Chuẩn MLflow (Format Normalization):**
   - Tiếp nhận mô hình từ quá trình huấn luyện tự động (`TrainingJob`) hoặc mô hình do người dùng tải lên thủ công (`Build`).
   - Tự động quét và nhận diện định dạng file mô hình: `.pkl`, `.joblib`, `.xgb`, `.pt`, `.pth`, `.h5`, `.keras`.
   - Tự động xác định loại mô hình (Model Flavor): `sklearn`, `xgboost`, `pytorch`, `tensorflow`, `keras` và chuẩn hóa về cấu trúc thư mục tiêu chuẩn MLflow Pyfunc (`MLmodel`).
2. **Tự động Sinh Dockerfile & Dependency Injection:**
   - Phân tích mã nguồn và các file phụ thuộc (`requirements.txt`, conda `environment.yml`).
   - Tự động lựa chọn Base Image tối ưu dựa trên flavor:
     - Mô hình Scikit-Learn / XGBoost $\rightarrow$ Dùng base image `machine-learning-serving` (FastAPI).
     - Mô hình Deep Learning PyTorch / TensorFlow $\rightarrow$ Dùng base image `deep-learning-serving` (BentoML).
   - Tự động sinh `Dockerfile` tối ưu nhiều tầng (Multi-stage) để đóng gói mã nguồn và mô hình vào container phục vụ.
3. **Cơ chế Xây dựng Image Đa Nền tảng (Multi-Engine Image Build):**
   - **Môi trường Cục bộ (`BUILD_ENGINE=docker`):** Sử dụng Docker SDK (`docker-py`) để giao tiếp trực tiếp với Docker Daemon, build image và lưu vào local registry.
   - **Môi trường Production K3s (`BUILD_ENGINE=kaniko`):** Chuẩn bị toàn bộ ngữ cảnh build vào thư mục chia sẻ `/workspace` để Kaniko Executor thực hiện build không cần quyền root (Rootless Container Build) và đẩy trực tiếp lên **Harbor OCI Registry**.
4. **Giám sát Tiến trình Thời gian thực & Báo cáo Trạng thái:**
   - Stream trực tiếp nhật ký build (từng dòng lệnh Docker/Kaniko) vào Redis (`build_logs:{build_id}`) để giao diện Web hiển thị trực tiếp cho người dùng.
   - Kết thúc tiến trình, gửi tín hiệu Webhook Callback kèm `Idempotency-Key` về Control Plane để cập nhật trạng thái `COMPLETED` hoặc `FAILED`.

```
                +---------------------------------------------+
                |     Control Plane (Dispatch Build Task)     |
                +---------------------------------------------+
                                       │
                      +----------------+----------------+
                      │                                 │
                      ▼ (Local Dev)                     ▼ (Production K3s)
             +------------------+             +--------------------+
             |  Docker Engine   |             |   Argo Workflow    |
             |   (Docker SDK)   |             | (Kaniko Rootless)  |
             +------------------+             +--------------------+
                      │                                 │
                      +----------------+----------------+
                                       │
                                       ▼
+-----------------------------------------------------------------------------+
|                               MODEL PACKAGER                                |
|                                                                             |
|  1. Tải Artifact từ S3 qua Presigned GET URL (Safe Extraction chống TarSlip)|
|  2. Nhận diện Model Flavor & Chuẩn hóa sang MLflow Pyfunc Format            |
|  3. Phân tích dependencies & Tự động sinh Dockerfile                        |
|  4. Build Container Image (image-{project_uuid}:build-{build_uuid})         |
|  5. Push Image lên Harbor Registry (Production) hoặc Docker Local Cache     |
|  6. Stream logs -> Redis (build_logs:{build_id})                            |
|  7. Gửi Webhook Callback -> Control Plane (/internal/webhooks/builds/<id>/) |
+-----------------------------------------------------------------------------+
```

---

### 1.2. Các thành phần chính

| Module / File | Trách nhiệm chính |
|---|---|
| **`src/main.py`** | Entrypoint mỏng khởi động tiến trình và quản lý mã thoát (Exit code). |
| **`src/tasks.py`** | Điều phối các luồng công việc chính dựa trên biến `TASK_TYPE`: `BUILD` (đóng gói và build ảnh), `TEST_ZIP` (kiểm tra tính hợp lệ của file nén), và `NOTIFY_BUILD` (gửi callback sau khi Kaniko hoàn thành). |
| **`src/core.py`** | Nhân xử lý cốt lõi: nạp mô hình thô, chuyển đổi sang MLflow format, phân tích `requirements.txt`, và tạo cấu trúc cây thư mục xem trước (`build_preview_tree`). |
| **`src/image_build.py`** | Quản lý logic build ảnh: tạo ngữ cảnh Docker build, cấu hình base image phù hợp, và tương tác với Docker Daemon API. |
| **`src/io.py`** | Tầng giao tiếp I/O an toàn: tải và đẩy file qua Presigned S3 URLs, giải nén TAR/ZIP an toàn (chống tấn công Directory Traversal), và gửi Webhook có xác thực Bearer Token. |
| **`src/config.py`** | Định nghĩa cấu hình môi trường, quy chuẩn đặt tên image và registry tag. |
| **`src/logging_utils.py`** | Quản lý stream log tới Redis (`build_logs:{build_id}`) và ghi nhật ký có cấu trúc ra stdout. |

---

### 1.3. Luồng hoạt động

#### Kịch bản 1: Môi trường Local (`BUILD_ENGINE=docker`)
1. Model Packager khởi động với biến `TASK_TYPE=BUILD`.
2. Tải artifact nén từ S3 thông qua `DOWNLOAD_URL` (Presigned GET URL).
3. Giải nén an toàn vào thư mục làm việc, phát hiện file mô hình và chuẩn hóa sang MLflow format.
4. Sinh `Dockerfile` phù hợp với flavor của mô hình.
5. Gọi Docker SDK build image với tag: `image-{project_id}:build-{build_id}`.
6. Mỗi dòng log trong quá trình build được đẩy trực tiếp vào Redis key `build_logs:{build_id}`.
7. Khi build thành công, gọi HTTP POST tới `WEBHOOK_URL` của Control Plane kèm thông tin image và mã xác thực `CONTROL_PLANE_WEBHOOK_SECRET`.

#### Kịch bản 2: Môi trường Production K3s (`BUILD_ENGINE=kaniko` qua Argo Workflow 3 bước)
```
Step 1: model-packager (TASK_TYPE=BUILD, BUILD_ENGINE=kaniko)
  ├── Tải artifact từ S3 và chuẩn hóa định dạng MLflow
  ├── Sinh Dockerfile và requirements.txt vào thư mục chia sẻ /workspace/
  └── Ghi file trạng thái chuẩn bị webhook_payload.json vào /workspace/

Step 2: kaniko-executor (Container của Google Kaniko)
  ├── Đọc /workspace/Dockerfile và ngữ cảnh build
  ├── Thực thi build image hoàn toàn không cần Docker daemon (Rootless)
  └── Đẩy container image trực tiếp lên Harbor Registry nội bộ

Step 3: model-packager (TASK_TYPE=NOTIFY_BUILD)
  ├── Đọc kết quả từ /workspace/webhook_payload.json
  └── Bắn Webhook Callback về Control Plane thông báo Build thành công
```

---

## 2. Cấu trúc cây thư mục

```text
services/model-packager/
├── Dockerfile                         # Khai báo image runtime cho Packager worker
├── requirements.txt                   # Danh sách thư viện (mlflow, docker, redis, requests)
├── src/                               # Toàn bộ mã nguồn nghiệp vụ
│   ├── __init__.py
│   ├── main.py                        # Entrypoint mỏng của tiến trình
│   ├── tasks.py                       # Điều phối các tác vụ BUILD, TEST_ZIP, NOTIFY_BUILD
│   ├── core.py                        # Nạp model, phân tích requirements và format MLflow
│   ├── image_build.py                 # Chuẩn bị ngữ cảnh và build container image
│   ├── io.py                          # Presigned S3 I/O, an toàn giải nén và Webhook HTTP
│   ├── config.py                      # Quản lý tên image, tag và biến môi trường
│   `-- logging_utils.py               # Redis log streaming và context-aware logging
`-- tests/                             # Bộ kiểm thử tự động độc lập
    ├── __init__.py
    ├── conftest.py                    # Khởi tạo mock S3, Docker và Redis fixtures
    ├── test_cli.py                    # Kiểm thử giao diện dòng lệnh và entrypoint
    ├── test_core.py                   # Kiểm thử logic nhận diện flavor và parse dependency
    ├── test_logging.py                # Kiểm thử cấu hình logger
    `-- test_logging_utils.py          # Kiểm thử cơ chế Redis Log Handler
```

---

## 3. Hướng dẫn khởi chạy và các lệnh cần thiết

### 3.1. Chạy thông qua Docker Compose (Môi trường phát triển cục bộ)

Model Packager thông thường được kích hoạt theo nhu cầu (On-Demand Task) bởi Control Plane. Tuy nhiên, bạn có thể chạy thử nghiệm đóng gói độc lập bằng Docker:

```bash
docker run --rm \
  -e TASK_TYPE=BUILD \
  -e BUILD_ENGINE=docker \
  -e BUILD_ID=019488a0-0000-7000-8000-000000000001 \
  -e PROJECT_ID=019488a0-0000-7000-8000-000000000002 \
  -e DOWNLOAD_URL="https://your-s3-presigned-get-url" \
  -e WEBHOOK_URL="http://control-plane:8000/internal/webhooks/builds/019488a0-0000-7000-8000-000000000001/" \
  -e CONTROL_PLANE_WEBHOOK_SECRET="local-webhook-secret" \
  -e REDIS_URL="redis://redis:6379/1" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  mlops-paas-model-packager:latest
```

### 3.2. Chạy thử nghiệm trực tiếp trên máy chủ / Virtualenv

#### Bước 1: Chuẩn bị môi trường ảo
```bash
cd services/model-packager
python -m venv .venv
# Trên Windows:
.venv\Scripts\Activate.ps1
# Trên Linux/macOS:
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

#### Bước 2: Thiết lập biến môi trường và chạy thử
```bash
export BUILD_ID=test-build-uuid
export PROJECT_ID=test-project-uuid
export TASK_TYPE=BUILD
export BUILD_ENGINE=docker

# Chạy tiến trình đóng gói
python -m src.main
```

---

### 3.3. Các biến môi trường quan trọng

| Tên biến | Bắt buộc | Mô tả chức năng |
|---|---|---|
| `BUILD_ID` | Có | UUID duy nhất xác định phiên bản đóng gói Build. |
| `PROJECT_ID` | Có | UUID của dự án sở hữu mô hình. |
| `TASK_TYPE` | Không | Loại tác vụ thực thi: `BUILD` (mặc định), `TEST_ZIP`, hoặc `NOTIFY_BUILD`. |
| `BUILD_ENGINE` | Không | Động cơ build: `docker` (local) hoặc `kaniko` (production). |
| `DOWNLOAD_URL` | Có | Presigned GET URL tải artifact mô hình từ S3. |
| `WEBHOOK_URL` | Có | URL nội bộ của Control Plane tiếp nhận callback trạng thái. |
| `CONTROL_PLANE_WEBHOOK_SECRET` | Có | Chuỗi bí mật xác thực webhook callback (Bearer token). |
| `REDIS_URL` | Không | Kết nối Redis để stream trực tiếp logs (`build_logs:{build_id}`). |
| `HARBOR_REGISTRY_URL` | K8s | Địa chỉ Harbor Registry để push container image (khi dùng Kaniko). |

---

### 3.4. Kiểm tra chất lượng & Chạy Unit Test (Quality Gates)

```bash
# 1. Kiểm tra linting với Ruff
python -m ruff check .

# 2. Chạy toàn bộ bộ kiểm thử tự động với Pytest
python -m pytest --cov=src --cov-report=term-missing
```

---

## 4. Các chú ý quan trọng (Architectural Constraints & Caveats)

> [!IMPORTANT]
> **Định Danh Bắt Buộc (Identifier Invariant):**
> Model Packager nhận diện phiên bản thực thi duy nhất thông qua `BUILD_ID`. Tuyệt đối không dùng chung hay thay thế biến này bằng các định danh khác như `MODEL_ID`.

> [!WARNING]
> **Bảo Mật Tệp Nén (Safe Archive Extraction):**
> Quá trình giải nén file artifact tải về (`safe_extract_tar` trong `src/io.py`) áp dụng bộ lọc an toàn nghiêm ngặt để triệt tiêu lỗ hổng **Zip/Tar Slip**. Toàn bộ các phần tử chứa đường dẫn tương đối trỏ ngược (`..`), đường dẫn tuyệt đối hoặc symbolic links trỏ ra ngoài thư mục đích đều bị từ chối và báo lỗi ngay lập tức.

> [!CAUTION]
> **Không Bỏ Qua Lỗi Cài Đặt Thư Viện Phụ Thuộc (Fail on Dependency Error):**
> Khi cài đặt `requirements.txt` của người dùng, nếu lệnh cài đặt gặp lỗi, tiến trình build bắt buộc phải đánh dấu thất bại (`FAIL`) và trả về log chi tiết. **Tuyệt đối không sử dụng lệnh dạng shell `pip install ... || echo "ignored"` để che giấu lỗi cài đặt**.

> [!TIP]
> **Bảo Mật Thông Tin Xác Thực (Zero AWS Credentials in Job):**
> Model Packager không bao giờ nhận thông tin tài khoản AWS (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) hay mật khẩu cơ sở dữ liệu. Toàn bộ thao tác tải/đẩy dữ liệu đều thông qua các đường dẫn Presigned S3 URLs được Control Plane cấp phát riêng với thời hạn hiệu lực ngắn.
