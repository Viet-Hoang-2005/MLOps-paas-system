# Django Control Plane — Hệ thống Điều phối Trung tâm MLOps PaaS

Thư mục `services/control-plane/` chứa mã nguồn của **Control Plane Service**, thành phần hạt nhân (Core Orchestrator) quản lý toàn bộ nghiệp vụ, định danh, trạng thái vòng đời mô hình học máy và điều phối tác vụ bất đồng bộ cho nền tảng MLOps PaaS.

---

## 1. Giới thiệu

### 1.1. Vai trò trong hệ thống

Trong kiến trúc tổng thể của MLOps PaaS, Control Plane được thiết kế theo mô hình **Domain-Oriented Modular Monolith** trên nền tảng Python (Django & Django REST Framework / Celery). Nó đóng vai trò là "Bộ não điều phối" (Brain of the System) với các trách nhiệm cốt lõi:

1. **Nguồn Chân lý Quan hệ (Relational Source of Truth):**
   - Sở hữu và quản lý toàn bộ lược đồ quan hệ trong schema PostgreSQL riêng biệt (`control_plane`), đảm bảo tính nhất quán dữ liệu (ACID) cho tất cả các đối tượng: người dùng, dự án, phiên bản mô hình, bài toán huấn luyện, tiến trình triển khai và lịch trình giám sát drift.
2. **Quản lý Định danh & Phân quyền Đa tầng (Identity & Access Management):**
   - Hỗ trợ xác thực người dùng bằng JWT (ký thuật toán bất đối xứng `RS256` với endpoint phân phối public key `JWKS`), OAuth2 (Google, GitHub), xác thực hai yếu tố (2FA/TOTP).
   - Cung cấp cơ chế API Key theo phạm vi dự án (`ApiKey`) cho các tác vụ CI/CD hoặc client gọi ngoài.
3. **Quản lý Vòng đời Học máy Toàn diện (End-to-End MLOps Lifecycle):**
   - **Model Catalog & Registry:** Quản lý tài sản không gian làm việc (Workspaces, Datasets, Feature Views) và kho lưu trữ phiên bản mô hình bất biến (`ModelVersion`, Artifacts, Metrics, Insights, Aliases như `champion`/`challenger`).
   - **Training Orchestration:** Khởi tạo, cấp phát quyền truy cập S3 qua Presigned URLs ngắn hạn, theo dõi tiến trình, lưu trữ snapshot và hỗ trợ hủy tác vụ huấn luyện (`TrainingJob`).
   - **Packaging & Deployment:** Điều phối đóng gói container image (`Build`), triển khai phục vụ suy luận (`Deployment`) và cấu hình định tuyến (`Endpoint`).
   - **Drift Monitoring & Continuous Training (CT):** Thiết lập màn hình giám sát (`DriftMonitor`), phân tích trôi dạt dữ liệu định kỳ hoặc theo sự kiện (`DriftRun` qua Evidently AI), và tự động kích hoạt tái huấn luyện (Retraining pipeline) khi phát hiện drift vượt ngưỡng.
4. **Kiến trúc Thực thi Đa hạ tầng (Multi-Backend Execution):**
   - Tách biệt hoàn toàn tầng điều phối nghiệp vụ với tầng hạ tầng thực thi. Hệ thống hỗ trợ chuyển đổi liền mạch giữa môi trường phát triển cục bộ (`docker` backend) và môi trường sản xuất phân tán trên Kubernetes (`argo` backend qua Argo Workflows & Argo Events) thông qua biến cấu hình môi trường.
5. **Cổng Quan sát & Nhật ký Thực thi (Observability & Runtime Logs):**
   - Cung cấp cổng proxy xác thực người dùng để truy vấn logs thực thi theo thời gian thực (Redis Streams cho local hoặc Grafana Loki có chữ ký số cursor cho production).

```
                      +---------------------------------------+
                      |       Web Frontend / REST Client      |
                      +---------------------------------------+
                                          |
                                    HTTPS / JWT
                                          v
                      +---------------------------------------+
                      |         Django Control Plane          |
                      |   (Modular Monolith - REST & WS)      |
                      +---------------------------------------+
                        |        |         |             |
       +----------------+        |         |             +-----------------+
       |                         |         |                               |
       v                         v         v                               v
+--------------+          +-----------+  +-------------------+    +----------------+
|  PostgreSQL  |          |   Redis   |  |   Celery Worker   |    |    AWS S3 /    |
| (Schema SSOT)|          | (Streams) |  | (Async Tasks)     |    | Presigned URLs |
+--------------+          +-----------+  +-------------------+    +----------------+
                                                   |
                             +---------------------+---------------------+
                             |                                           |
                             v (Local Dev)                               v (Production)
                    +------------------+                       +-------------------+
                    |  Docker Engine   |                       |  Argo Workflows   |
                    | (Containers API) |                       | & Argo Events K8s |
                    +------------------+                       +-------------------+
```

---

### 1.2. Các thành phần chính

Control Plane được module hóa thành 10 ứng dụng chuyên biệt (`apps/`) bên cạnh các lớp hạ tầng và tiện ích dùng chung:

| Ứng dụng / Module | Thư mục | Trách nhiệm chính |
|---|---|---|
| **`apps.auth`** | `src/apps/auth/` | Quản lý người dùng (`CustomUser`), JWT token phát hành/thu hồi, JWKS server, đăng nhập OAuth2 (Google/GitHub), 2FA/TOTP. |
| **`apps.access`** | `src/apps/access/` | Quản lý API Key theo từng dự án (`ApiKey`), băm khóa bảo mật `SHA-256`, kiểm tra quyền hạn client máy-đối-máy. |
| **`apps.catalog`** | `src/apps/catalog/` | Quản lý dự án (`ModelProject`), dataset nguồn, feature views, metadata linh hoạt và cơ chế dọn dẹp dự án bất đồng bộ. |
| **`apps.registry`** | `src/apps/registry/` | Quản lý phiên bản mô hình bất biến (`ModelVersion`), lưu trữ liên kết artifacts S3, metric kiểm thử, giải thích mô hình (insights) và alias động (`champion`). |
| **`apps.training`** | `src/apps/training/` | Quản lý các bài toán huấn luyện (`TrainingJob`), sinh Capability Token và Presigned S3 URLs cho container huấn luyện, hủy job an toàn. |
| **`apps.deployment`** | `src/apps/deployment/` | Quản lý quy trình build container (`Build`), tạo bản triển khai serving (`Deployment`), định tuyến (`Endpoint`), hỗ trợ triển khai Docker/Kubernetes. |
| **`apps.drift`** | `src/apps/drift/` | Thiết lập bộ giám sát trôi dạt (`DriftMonitor`), tạo phiên phân tích trôi dạt (`DriftRun`), nhận kết quả từ worker Evidently AI. |
| **`apps.ct`** | `src/apps/ct/` | Điều phối tái huấn luyện liên tục (Continuous Training), kích hoạt các pipeline huấn luyện mới dựa trên tín hiệu drift hoặc tích lũy dữ liệu sản xuất. |
| **`apps.production`** | `src/apps/production/` | Lưu trữ bản ghi suy luận thực tế thu thập từ production (`ProductionPredictionRecord`) phục vụ giám sát và phân tích drift. |
| **`apps.observability`** | `src/apps/observability/` | Kiểm tra sức khỏe hệ thống (`/health/live`, `/health/ready`), Prometheus metrics (`/health/metrics`), Event Outbox pattern, và Proxy bảo mật cho runtime logs. |
| **`infrastructure`** | `src/infrastructure/` | Các adapter kết nối ngoại vi: `docker.py`, `argo.py` (Argo Events webhook client), `harbor.py` (Harbor OCI API), `redpanda.py`, `runtime_logs.py`, `prometheus.py`. |
| **`common`** | `src/common/` | Bộ lọc middleware (`RequestContextMiddleware`), định dạng logs JSON/Console, chuẩn hóa pagination, custom exception handling, Redis connection factory. |

---

### 1.3. Luồng hoạt động

Mọi luồng xử lý ghi trạng thái trong Control Plane đều tuân thủ nghiêm ngặt **Quy tắc phân tầng và ranh giới kiến trúc (Strict Boundary Pattern)**:

```
[HTTP Request] 
      │
      ▼
[API View / Serializer]  ──► Xác thực danh tính, kiểm tra cú pháp payload
      │
      ▼
[Selector / Service]     ──► Kiểm tra quyền sở hữu Tenant, kiểm tra logic nghiệp vụ
      │
      ▼
[transaction.atomic]     ──► Ghi DB PostgreSQL, cập nhật trạng thái (Pending/Running)
      │
      ▼
[transaction.on_commit]  ──► Chỉ kích hoạt Celery Task SAU KHI DB ĐÃ COMMIT THÀNH CÔNG
      │
      ▼
[Celery Worker Task]     ──► Gọi Execution Backend Factory (Docker hoặc Argo)
      │
      ▼
[Worker Execution]       ──► Container chạy bên ngoài (Training Runner / Packager / Evidently)
      │
      ▼
[Internal Webhook]       ──► Container gọi ngược về Control Plane với Idempotency-Key
      │
      ▼
[Callback Handler]       ──► Khóa row bằng select_for_update(), cập nhật trạng thái cuối cùng (Succeeded/Failed)
```

#### Chi tiết các luồng chính:

1. **Luồng Huấn luyện Mô hình (Training Workflow):**
   - Client gửi yêu cầu huấn luyện `POST /api/training-jobs/`.
   - Control Plane lưu job với trạng thái `PENDING`, sinh Capability Token (JWT ngắn hạn mã hóa quyền hạn và UUID của job).
   - Hook `on_commit` đẩy tác vụ `dispatch_training_job` vào hàng đợi Celery.
   - Celery worker kích hoạt container huấn luyện:
     - Nếu là môi trường `docker`: Khởi chạy container `training-runner` trên mạng Docker nội bộ.
     - Nếu là môi trường `argo`: Bắn webhook tới Argo Events EventSource để khởi chạy Kubernetes `Workflow` hoặc Kubeflow `PyTorchJob`.
   - `training-runner` khởi động, dùng token gọi Control Plane lấy Presigned URL tải mã nguồn/dữ liệu và Presigned URL tải artifacts kết quả lên S3.
   - Khi hoàn tất, `training-runner` gọi callback `POST /internal/webhooks/training-jobs/<uuid>/`. Control Plane kiểm tra token, cập nhật trạng thái `COMPLETED`, không tự đăng ký version. Source/data/reference của job được đóng băng; retry tạo job mới từ snapshot gốc.

2. **Luồng Đóng gói & Triển khai (Build & Deploy Workflow):**
   - Khi người dùng muốn phục vụ mô hình: Client tạo `Build` từ revision Preview (`POST /api/models/<project>/builds/`) hoặc output TrainingJob completed (`POST /api/training-jobs/<job>/build/`).
   - Celery giao việc cho `model-packager` để tải model artifact từ S3, tạo Dockerfile tối ưu (hỗ trợ MLflow / Sklearn / PyTorch) và đẩy container image lên Harbor Registry (hoặc Docker daemon nội bộ).
   - Callback chỉ hoàn tất Build. Người dùng gọi `POST /api/builds/<build>/register/` để tạo snapshot Evolution idempotent; sau đó mới gọi `POST /api/deployments/`.
   - Control Plane điều phối:
     - Với Docker: Dựng container phục vụ suy luận (`machine-learning-serving` hoặc `deep-learning-serving`) nối vào mạng nội bộ.
     - Với Argo/K8s: Kích hoạt triển khai Deployment/Pod trên namespace `mlops-model-runtimes` được quản lý bởi K3s Traefik.
   - Chỉ sau readiness mới chuyển `ModelProject.active_deployment`; gateway/Overview/Monitoring dùng chung pointer này. Bản mới lỗi không thay Running cũ. Runtime đặt tên theo deployment UUID; dừng bản cũ sau handoff.

3. **Luồng Giám sát Drift & Tự động Kích hoạt (Drift & CT Workflow):**
   - Service `consumer` đọc dữ liệu suy luận thực tế từ topic Kafka `mlops_paas_production_data`, lưu vào bảng `production_predictionrecord`.
   - Sau mỗi batch ingest thành công, dispatcher outbox của `consumer` gửi signal tới webhook `POST /internal/webhooks/automatic-drift/`.
   - Control Plane kiểm tra `DriftMonitor`, khởi tạo `DriftRun` và ủy quyền cho `evidently` runner thực thi phân tích trôi dạt so sánh giữa dữ liệu suy luận và dữ liệu baseline trên S3.
   - `evidently` báo cáo kết quả qua callback webhook `POST /internal/webhooks/drift-runs/<uuid>/`. Nếu drift vượt ngưỡng an toàn đã cấu hình, module `apps.ct` sẽ tự động kích hoạt một `TrainingJob` mới để huấn luyện lại mô hình với dữ liệu cập nhật.

---

## 2. Cấu trúc cây thư mục

```text
services/control-plane/
├── Dockerfile                         # Khai báo container runtime cho Control Plane
├── manage.py                          # Django management CLI entrypoint
├── pyproject.toml                     # Cấu hình công cụ phát triển (Ruff, pytest)
├── requirements.txt                   # Danh sách thư viện Python phụ thuộc
├── staticfiles/                       # Thư mục chứa static files thu thập bởi collectstatic
`-- src/
    ├── config/                        # Cấu hình dự án Django & Celery
    │   ├── asgi.py                    # Cấu hình ASGI (hỗ trợ Channels/WebSockets)
    │   ├── wsgi.py                    # Cấu hình WSGI tiêu chuẩn cho Gunicorn
    │   ├── celery.py                  # Khởi tạo instance Celery app
    │   ├── urls.py                    # Root URL router kết nối toàn bộ public API và webhooks
    │   `-- settings/                  # Cấu hình đa môi trường
    │       ├── base.py                # Cài đặt nền tảng: apps, DB, auth, storage, execution
    │       ├── local.py               # Cài đặt tối ưu cho Docker Compose / Local Dev
    │       ├── production.py          # Cài đặt khắt khe cho K3s Production (HSTS, SSL, JWKS, IP Allowlist)
    │       `-- test.py                # Cài đặt cho unit test (In-memory DB, Eager Celery, Mock S3)
    ├── common/                        # Tiện ích chia sẻ nội bộ
    │   ├── env.py                     # Tiện ích đọc biến môi trường an toàn kiểu dữ liệu
    │   ├── middleware.py              # RequestContextMiddleware đính kèm requestId & tenant context
    │   ├── logging.py                 # Cấu hình định dạng logger (Console hoặc JSON một dòng)
    │   ├── logging_utils.py           # Tiện ích trích xuất và format log theo chuẩn hệ thống
    │   ├── celery_logging.py          # Đồng bộ định dạng log giữa Django và Celery worker
    │   ├── gunicorn_conf.py           # Cấu hình worker, bind port và metrics cho Gunicorn
    │   ├── metrics.py                 # Định nghĩa Prometheus Metrics (HTTP latency, counter, Gauges)
    │   └── redis_client.py            # Quản lý kết nối Redis (hỗ trợ Direct và Redis Sentinel HA)
    ├── infrastructure/                # Các Adapter tương tác với dịch vụ bên ngoài
    │   ├── docker.py                  # Client giao tiếp Docker Daemon (local execution)
    │   ├── argo.py                    # Client phát webhook kích hoạt Argo Events (K8s execution)
    │   ├── harbor.py                  # Client quản lý dự án và images trên Harbor Registry
    │   ├── redpanda.py                # Producer đẩy sự kiện vào hàng đợi Redpanda Kafka
    │   ├── runtime_logs.py            # Client xử lý streaming logs từ Redis / Loki
    │   ├── prometheus.py              # Client truy vấn số liệu giám sát từ Prometheus
    │   `-- http.py                    # Tiện ích HTTP request có tích hợp retry và timeout
    `-- apps/                          # 10 Module chức năng độc lập
        ├── auth/                      # Quản lý định danh người dùng và xác thực
        ├── access/                    # Quản lý scoped API Keys
        ├── catalog/                   # Dự án, không gian làm việc và metadata
        ├── registry/                  # Đăng ký và quản lý phiên bản mô hình bất biến
        ├── training/                  # Quản lý bài toán và tiến trình huấn luyện
        ├── deployment/                # Quy trình Build ảnh và Deployment serving
        ├── drift/                     # Quản lý và thực thi giám sát trôi dạt dữ liệu
        ├── ct/                        # Kích hoạt quy trình Continuous Training tự động
        ├── production/                # Lưu trữ bản ghi suy luận thực tế
        `-- observability/             # Endpoints kiểm tra sức khỏe, Outbox và Log Proxy
```

> [!NOTE]
> Bên trong mỗi thư mục con của `src/apps/<tên-app>/`, cấu trúc đều được chuẩn hóa theo chuẩn kiến trúc:
> - `models.py`: Khai báo bảng dữ liệu với khóa chính UUID và schema `control_plane`.
> - `selectors.py`: Chứa toàn bộ các hàm **truy vấn đọc (Read-only queries)**, luôn lọc theo tenant/user sở hữu.
> - `services/`: Chứa các hàm **thực thi nghiệp vụ và ghi dữ liệu (Write operations)**, đảm bảo bọc trong `transaction.atomic()`.
> - `tasks.py`: Các Celery tasks thực hiện điều phối tác vụ nền bất đồng bộ.
> - `api/`: Phân tách rõ ràng giữa `endpoints.py` (REST views), `serializers.py` (validate & format dữ liệu), `urls.py` và `webhooks.py` (nhận tín hiệu callback nội bộ).
> - `tests/`: Bộ kiểm thử đơn vị độc lập, không phụ thuộc mạng ngoài.

---

## 3. Hướng dẫn khởi chạy và các lệnh cần thiết

Workflow mới dùng Project + Preview 1–1, snapshot Build/Version bất biến và Running tường minh. Không backfill dữ liệu cũ. Đọc [runbook clean bootstrap local](../../docs/dev/web-workflow-local.md) trước khi khởi động lại trên database đang có; không tự xóa volume. Xóa project là cleanup bất đồng bộ retryable, chỉ hard-delete DB sau khi runtime/object/image thuộc project đã được dọn.

### 3.1. Khởi chạy bằng Docker Compose (Môi trường phát triển cục bộ)

Đây là phương thức chuẩn nhất để khởi chạy Control Plane cùng toàn bộ hệ sinh thái phụ trợ (PostgreSQL, Redis, Redpanda, Celery):

```bash
# Khởi động Control Plane và Celery Worker ở chế độ nền
docker compose up -d control-plane celery-worker

# Xem logs trực tiếp của Control Plane
docker compose logs -f control-plane

# Xem logs trực tiếp của Celery Worker
docker compose logs -f celery-worker
```

Kiểm tra trạng thái sẵn sàng của dịch vụ:
```bash
# Kiểm tra liveness
curl http://localhost:8000/health/live

# Kiểm tra readiness (kết nối DB, Redis, v.v.)
curl http://localhost:8000/health/ready
```

---

### 3.2. Khởi chạy trực tiếp trên máy chủ / Virtualenv (Không dùng Docker)

Dành cho nhà phát triển muốn debug trực tiếp mã nguồn bằng Python:

#### Bước 1: Chuẩn bị môi trường ảo
```bash
# Chuyển vào thư mục service
cd services/control-plane

# Tạo và kích hoạt môi trường ảo Python 3.12+
python -m venv .venv
# Trên Windows:
.venv\Scripts\Activate.ps1
# Trên Linux/macOS:
source .venv/bin/activate

# Cài đặt các thư viện phụ thuộc
pip install --upgrade pip
pip install -r requirements.txt
```

#### Bước 2: Cấu hình biến môi trường
Tạo file `.env` hoặc thiết lập trực tiếp biến môi trường:
```bash
export DJANGO_SETTINGS_MODULE=config.settings.local
export DB_HOST_RW=localhost
export DB_PORT=5432
export DB_NAME=mlops_paas_db
export DB_USER=postgres
export DB_PASSWORD=postgres
export REDIS_URL=redis://localhost:6379/1
export CELERY_BROKER_URL=redis://localhost:6379/3
export CELERY_RESULT_BACKEND=redis://localhost:6379/4
```

#### Bước 3: Đồng bộ cơ sở dữ liệu và khởi tạo dữ liệu
```bash
# Thực hiện migrate schema
python manage.py migrate --settings=config.settings.local

# Tạo tài khoản quản trị (Superuser)
python manage.py createsuperuser --settings=config.settings.local
```

#### Bước 4: Chạy máy chủ phát triển và Worker
Mở 2 cửa sổ terminal riêng biệt:

*Terminal 1 (Django API Server):*
```bash
python manage.py runserver 0.0.0.0:8000 --settings=config.settings.local
```

*Terminal 2 (Celery Background Worker):*
```bash
celery -A config worker --loglevel=info
```

---

### 3.3. Các lệnh kiểm tra chất lượng (Quality Gates & Testing)

Trước khi commit mã nguồn, cần vượt qua các bài kiểm tra chất lượng theo chuẩn của hệ thống:

```bash
# 1. Kiểm tra Linting và quy chuẩn định dạng mã nguồn với Ruff
python -m ruff check .

# 2. Chạy toàn bộ bộ kiểm thử đơn vị và tích hợp với Pytest
python -m pytest

# 3. Kiểm tra tính toàn vẹn của cấu hình Django
python manage.py check --settings=config.settings.test

# 4. Kiểm tra phát hiện xung đột hoặc thiếu sót trong file migrations (Dry-run)
python manage.py makemigrations --check --dry-run --settings=config.settings.test
```

---

## 4. Các chú ý quan trọng (Architectural Constraints & Caveats)

> [!IMPORTANT]
> **Ranh giới phân tầng bất biến (Layering Boundary):**
> Các file trong thư mục `api/` (Endpoints, Views, Serializers) **TUYỆT ĐỐI KHÔNG ĐƯỢC PHÉP** gọi trực tiếp các client hạ tầng như Docker SDK (`src/infrastructure/docker.py`), AWS S3 Boto3, Argo Events, Harbor, hay Redis. 
> Mọi thao tác ghi phải thông qua tầng `services/`, và mọi tác vụ mất thời gian/tương tác mạng ngoài bắt buộc phải được điều phối qua Celery Task tại ranh giới `transaction.on_commit`.

> [!WARNING]
> **Tính Idempotent của Webhook Callbacks & Chống hồi sinh trạng thái (No Resurrection):**
> 1. Mọi webhook nội bộ (`internal/webhooks/...`) nhận tín hiệu từ các worker container (Training, Build, Deploy, Drift) bắt buộc phải kiểm tra `Idempotency-Key` và dùng `select_for_update()` khi chuyển trạng thái terminal (`SUCCEEDED`, `FAILED`, `CANCELLED`).
> 2. Các callback đến muộn (Late callbacks) khi tài nguyên đã chuyển sang trạng thái hủy (`CANCELLED`) hoặc đang bị xóa (`DELETING`) **tuyệt đối không được phép hồi sinh (resurrect)** tài nguyên trở lại trạng thái thành công hoặc thất bại. Phải coi callback đó là no-op và trả về mã thành công 2xx để worker kết thúc chu kỳ retry.

> [!CAUTION]
> **Không Fallback cho Khóa Nhận diện Cũ:**
> Hệ thống tuân thủ nghiêm ngặt định danh chuẩn theo hợp đồng dịch vụ:
> - Model Packager: Bắt buộc dùng `BUILD_ID`.
> - Serving & Evidently: Bắt buộc dùng cặp `PROJECT_ID` và `MODEL_VERSION_ID`.
> - Training Runner: Bắt buộc dùng `TRAINING_JOB_ID`.
> Không bao giờ được phép thêm logic fallback cho biến cũ không tường minh như `MODEL_ID`.

> [!TIP]
> **Quản lý Logs Thực thi (Runtime Logs Architecture):**
> - **Redis Streams** chỉ được sử dụng làm bộ đệm tạm thời (transient presentation state) để phục vụ UI streaming logs realtime. PostgreSQL luôn là nguồn chân lý duy nhất cho trạng thái của tài nguyên.
> - Trên môi trường Production Kubernetes, logs tác vụ của Argo được lưu trữ tập trung trên **Grafana Loki** (thời gian lưu trữ 7 ngày). Control Plane đóng vai trò là Proxy bảo mật, tự động ký token con trỏ (signed task-bound cursor) để ngăn chặn việc người dùng lợi dụng LogQL để truy vấn trộm log của tenant khác.

Metric runtime local dùng `infrastructure/docker_metrics.py` đọc CPU/RAM bằng Docker SDK cho đúng deployment Running và kiểm tra đủ label owner. API `/api/observability/models/<project>/runtime-metrics/` trả snapshot, không lưu lịch sử. RPS dùng counter gateway atomic ngắn hạn trong Redis; Web giữ tối đa 5 phút trong bộ nhớ lúc mở trang. Không cần Prometheus/cAdvisor local; adapter Prometheus production được giữ nguyên.

> [!NOTE]
> **Chế độ Kết nối Redis (Redis Direct vs. Redis Sentinel):**
> Biến môi trường `REDIS_CONNECTION_MODE` quyết định phương thức kết nối:
> - `direct`: Sử dụng kết nối đơn trực tiếp (dùng cho Docker Compose local qua `REDIS_URL`).
> - `sentinel`: Sử dụng cho cụm Redis HA trên K3s sản xuất. Khi chọn chế độ này, bắt buộc phải cung cấp đủ các biến `REDIS_SENTINEL_HOSTS` (tối thiểu 3 node), `REDIS_SENTINEL_MASTER_NAME`, `REDIS_PASSWORD` và `REDIS_SENTINEL_PASSWORD`.
