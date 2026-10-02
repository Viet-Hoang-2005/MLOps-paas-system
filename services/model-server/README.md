# Model Server — Cổng Định Tuyến Suy Luận Tập Trung (Inference Gateway)

Thư mục `services/model-server/` chứa mã nguồn của **Model Server Service**, một Reverse Proxy / API Gateway hiệu năng cao dựa trên FastAPI. Dịch vụ đóng vai trò là điểm tiếp nhận lưu lượng dự đoán tập trung (Single Entrypoint) cho toàn bộ hệ thống phục vụ mô hình học máy của nền tảng MLOps PaaS.

---

## 1. Giới thiệu

### 1.1. Vai trò trong hệ thống

Trong kiến trúc MLOps PaaS, các worker phục vụ mô hình (`machine-learning-serving`, `deep-learning-serving` hoặc container đóng gói bởi `model-packager`) được thiết kế phi trạng thái (stateless) và không tích hợp sẵn tầng xác thực để tối ưu hóa hiệu năng tính toán. **Model Server** đóng vai trò là "Người gác cổng tin cậy" (Trusted Inference Gateway) với các trọng trách cốt lõi:

1. **Điểm đón đầu lưu lượng suy luận tập trung (Centralized Ingress for Inference):**
   - Cung cấp một giao diện API duy nhất cho các ứng dụng client (Web Dashboard, ứng dụng bên thứ ba, hệ thống CI/CD) truy vấn dự đoán mô hình thông qua đường dẫn chuẩn: `POST /models/{version_id}/predict`.
2. **Xác thực & Phân quyền Đa phương thức (Multi-Modal Auth & Access Control):**
   - Kiểm tra quyền truy cập mô hình dựa trên chế độ bảo vệ (`public`, `protected`, `private`).
   - Xác thực người dùng thông qua Bearer Token JWT (sử dụng thuật toán `RS256`, tự động tải và cache khóa công khai từ endpoint JWKS của Control Plane: `/api/auth/.well-known/jwks.json`).
   - Xác thực ứng dụng máy-đối-máy thông qua Project-scoped API Key (`X-API-Key`).
   - Tối ưu hóa kiểm tra quyền bằng bộ đệm phân tán Redis (tránh việc truy vấn cơ sở dữ liệu trên mỗi request suy luận).
3. **Định tuyến Động Đa Môi trường (Dynamic Multi-Environment Routing):**
   - Phân giải URL của worker phục vụ dựa trên môi trường triển khai thực tế:
     - Trên **Docker Compose**: Định tuyến trực tiếp tới tên container/dịch vụ nội bộ (ví dụ: `http://machine-learning-serving:5001/predict`).
     - Trên **Kubernetes (K3s)**: Định tuyến qua DNS nội bộ cụm K8s tới Service/Pod tương ứng trong namespace `mlops-model-runtimes` (ví dụ: `http://deployment-<id>.mlops-model-runtimes.svc.cluster.local:5000/predict`).
4. **Thu thập Dữ liệu Viễn thám Sản xuất (Production Telemetry Ingestion):**
   - Sau khi nhận kết quả dự đoán thành công từ worker, Model Server tự động đóng gói sự kiện suy luận (bao gồm: `tenant_id`, `project_id`, `model_version_id`, `features`, `prediction`, `confidence`, `latency_ms`, `request_id`) và đẩy bất đồng bộ (`BackgroundTasks`) vào hàng đợi Kafka / Redpanda (topic `mlops_paas_production_data`).
   - Dữ liệu này sau đó sẽ được `consumer` thu thập để phục vụ việc giám sát trôi dạt dữ liệu (Drift Detection) và Continuous Training.

```
                      +---------------------------------------+
                      |       Client / Frontend / External    |
                      +---------------------------------------+
                                          │
                                          │ POST /models/{version_id}/predict
                                          │ Headers: Authorization / X-API-Key
                                          ▼
                      +---------------------------------------+
                      |             MODEL SERVER              |
                      |          (Inference Gateway)          |
                      +---------------------------------------+
                         │                   │               │
      (1. Verify Token   │                   │ (2. Route     │ (4. Async Publish
       via JWKS / Redis) │                   │  Request)     │  Production Event)
                         ▼                   ▼               ▼
                +-----------------+  +---------------+  +---------------------+
                |  Control Plane  |  | Serving Pods  |  |   Redpanda Kafka    |
                |  JWKS / DB /    |  |  - ML Serving |  | (Topic: production) |
                |  Redis Cache    |  |  - DL Serving |  +---------------------+
                +-----------------+  +---------------+             │
                                             │                     │
                                     (3. Prediction                ▼
                                         Result)            +--------------+
                                                            |   Consumer   |
                                                            +--------------+
```

---

### 1.2. Các thành phần chính

| Module / File | Trách nhiệm chính |
|---|---|
| **`src/main.py`** | Entrypoint mỏng (Thin ASGI Entrypoint), nạp ứng dụng FastAPI từ `src.api:app`. |
| **`src/api.py`** | Router chính của gateway: quản lý vòng đời ứng dụng (`lifespan`), khởi tạo kết nối Redis / Kafka / DB, khai báo các endpoints (`/`, `/models/{version_id}/health`, `/models/{version_id}/predict`). |
| **`src/auth.py`** | Xử lý logic ủy quyền và xác thực: lấy và cache JWKS từ Control Plane, xác thực JWT RS256, kiểm tra tính hợp lệ của Project API Key, kiểm tra quyền sở hữu Tenant. |
| **`src/routing.py`** | Xử lý logic định tuyến: đọc cấu hình Deployment/Endpoint từ metadata mô hình để sinh ra URL nội bộ chính xác trỏ đến worker container (tương thích cả Docker và Kubernetes). |
| **`src/events.py`** | Quản lý Producer Kafka/Redpanda: đóng gói payload sự kiện suy luận, gửi tin nhắn bất đồng bộ, xử lý ghi nhận số liệu và log tóm tắt mà không gây gián đoạn luồng chính. |
| **`src/database.py`** | Tầng truy cập dữ liệu PostgreSQL & Redis Cache: đọc metadata phiên bản mô hình (`registry_modelversion`) và API Key (`access_apikey`), quản lý invalidation cache khi có thay đổi. |
| **`src/schemas.py`** | Khai báo các mô hình Pydantic validate dữ liệu đầu vào (`InferenceRequest`) và cấu trúc phản hồi chuẩn. |
| **`src/logging_utils.py`** | Middleware ghi vết request (`RequestLoggingMiddleware`), tự động gắn ngữ cảnh phân tán (`request_id`, `tenant_id`, `project_id`, `model_version_id`) vào log chuẩn hóa. |

---

### 1.3. Luồng hoạt động

1. **Tiếp nhận Request & Gắn ngữ cảnh:**
   - Client gửi request `POST /models/{version_id}/predict`.
   - Middleware ghi nhận `X-Request-ID` (hoặc tự sinh UUID mới), khởi tạo ngữ cảnh log.
2. **Xác thực và Phân quyền (`verify_model_access`):**
   - Tra cứu cache Redis để lấy thông tin phiên bản mô hình theo `version_id`. Nếu cache miss, truy vấn PostgreSQL schema `control_plane` và nạp vào Redis.
   - Kiểm tra chế độ bảo vệ (`access_mode`):
     - `public`: Cho phép truy cập không cần xác thực.
     - `protected` hoặc `private`: Bắt buộc kiểm tra JWT (Bearer Token) hoặc API Key (`X-API-Key`).
   - Nếu dùng JWT: Xác thực chữ ký token bằng Public Key lấy từ endpoint JWKS của Control Plane.
   - Nếu dùng API Key: Băm khóa với `SHA-256` và đối chiếu với bản ghi trong cơ sở dữ liệu/Redis cache.
3. **Phân giải Địa chỉ Worker (`resolve_worker_url`):**
   - Xác định môi trường thực thi (Docker hay K8s).
   - Xây dựng URL worker đích (ví dụ: `http://machine-learning-serving:5001/predict`).
4. **Proxy Request sang Worker Runtime:**
   - Sử dụng client bất đồng bộ `httpx.AsyncClient` chuyển tiếp payload `{ "features": ..., "model_version_id": ... }` tới worker kèm header `X-Request-ID`.
   - Đo đạc thời gian phản hồi thực tế (`latency_ms`).
5. **Trả kết quả & Bắn Telemetry Event:**
   - Trả kết quả dự đoán (prediction, status code, format chuẩn) về cho client ngay lập tức.
   - Đưa tác vụ `send_to_redpanda` vào hàng đợi `BackgroundTasks` để đẩy sự kiện telemetry vào topic Redpanda `mlops_paas_production_data`.

---

## 2. Cấu trúc cây thư mục

```text
services/model-server/
├── Dockerfile                         # Khai báo image runtime cho Model Server Gateway
├── requirements.txt                   # Danh sách thư viện Python phụ thuộc
├── ruff.toml                          # Cấu hình linter và formatter Ruff
├── src/                               # Toàn bộ mã nguồn nghiệp vụ
│   ├── __init__.py
│   ├── main.py                        # ASGI entrypoint cho Uvicorn / Gunicorn
│   ├── api.py                         # FastAPI App, routes, lifespan và dependency injection
│   ├── auth.py                        # Xử lý xác thực JWT (RS256/JWKS) và Project API Key
│   ├── database.py                    # Kết nối DB PostgreSQL và tầng Redis Cache
│   ├── events.py                      # Kafka Producer đẩy dữ liệu viễn thám sản xuất
│   ├── inference.py                   # Chuẩn hóa và parse kết quả trả về từ worker
│   ├── routing.py                     # Thuật toán phân giải URL nội bộ của worker
│   ├── schemas.py                     # Định nghĩa Pydantic models cho request / response
│   ├── uvicorn_entrypoint.py          # Script khởi chạy server Uvicorn
│   `-- logging_utils.py               # Middleware và tiện ích logging ngữ cảnh phân tán
`-- tests/                             # Bộ kiểm thử tự động
    ├── __init__.py
    ├── asgi_smoke.py                  # Smoke test cho ASGI application
    ├── test_database.py               # Kiểm thử truy vấn DB và cache
    ├── test_gateway.py                # Kiểm thử các luồng định tuyến và xác thực của Gateway
    ├── test_logging.py                # Kiểm thử định dạng log Console / JSON
    ├── test_logging_utils.py          # Kiểm thử middleware và context propagation
    `-- test_redis_sentinel.py         # Kiểm thử khả năng chịu lỗi với Redis Sentinel HA
```

---

## 3. Hướng dẫn khởi chạy và các lệnh cần thiết

### 3.1. Khởi chạy bằng Docker Compose (Môi trường phát triển cục bộ)

Model Server được cấu hình sẵn trong `docker-compose.yml` (chạy trên cổng `5002`):

```bash
# Khởi động Model Server cùng các dịch vụ phụ trợ
docker compose up -d model-server

# Theo dõi logs trực tiếp
docker compose logs -f model-server
```

Kiểm tra trạng thái sức khỏe của Gateway:
```bash
curl http://localhost:5002/
```

### 3.2. Khởi chạy trực tiếp trên máy chủ / Virtualenv (Không dùng Docker)

#### Bước 1: Chuẩn bị môi trường ảo
```bash
# Chuyển vào thư mục service
cd services/model-server

# Tạo và kích hoạt môi trường ảo Python 3.12+
python -m venv .venv
# Trên Windows:
.venv\Scripts\Activate.ps1
# Trên Linux/macOS:
source .venv/bin/activate

# Cài đặt các gói phụ thuộc
pip install --upgrade pip
pip install -r requirements.txt
```

#### Bước 2: Thiết lập biến môi trường
```bash
export DB_USER=postgres
export DB_PASSWORD=postgres
export DB_HOST_RO=localhost
export DB_PORT=5432
export DB_NAME=mlops_paas_db
export DB_SCHEMA=control_plane
export REDIS_URL=redis://localhost:6379/1
export REDIS_CONNECTION_MODE=direct
export REDPANDA_BROKERS=localhost:19092
export KAFKA_TOPIC=mlops_paas_production_data
export JWKS_URL=http://localhost:8000/api/auth/.well-known/jwks.json
```

#### Bước 3: Khởi chạy Gateway Server
```bash
uvicorn src.main:app --host 0.0.0.0 --port 5002 --reload
```

---

### 3.3. Các biến môi trường quan trọng

| Tên biến | Giá trị mặc định | Mô tả chức năng |
|---|---|---|
| `JWKS_URL` | `http://control-plane:8000/api/auth/.well-known/jwks.json` | URL endpoint lấy public key JWKS để xác thực chữ ký JWT RS256. |
| `REDPANDA_BROKERS` | `redpanda:9092` | Danh sách địa chỉ broker của Redpanda / Kafka. |
| `KAFKA_TOPIC` | `mlops_paas_production_data` | Topic tiếp nhận các sự kiện suy luận thành công. |
| `REDIS_URL` | `redis://redis:6379/1` | Địa chỉ kết nối Redis đơn lẻ (cho môi trường local). |
| `REDIS_CONNECTION_MODE` | `direct` | Chế độ kết nối Redis (`direct` hoặc `sentinel`). |
| `REDIS_SENTINEL_HOSTS` | `""` | Danh sách các node Sentinel (dùng cho production K3s HA). |
| `REDIS_SENTINEL_MASTER_NAME`| `""` | Tên cụm master trong Redis Sentinel. |
| `DB_HOST_RO` / `DB_PORT` | `postgres` / `5432` | Kết nối cơ sở dữ liệu PostgreSQL (Read-Only) để tra cứu thông tin mô hình. |

---

### 3.4. Kiểm tra chất lượng & Chạy Unit Test (Quality Gates)

```bash
# 1. Kiểm tra Linting và chuẩn code với Ruff
python -m ruff check .

# 2. Chạy toàn bộ bộ kiểm thử tự động với Pytest
python -m pytest --cov=src --cov-report=term-missing
```

---

## 4. Các chú ý quan trọng (Architectural Constraints & Caveats)

> [!IMPORTANT]
> **Tách Biệt Trách Nhiệm Xác Thực (Auth Gateway Boundary):**
> Model Server là **thành phần duy nhất chịu trách nhiệm xác thực và kiểm tra quyền** cho các yêu cầu suy luận. Các worker runtime (`machine-learning-serving`, `deep-learning-serving`) là các dịch vụ phi trạng thái, nằm trong mạng nội bộ bảo vệ và tuyệt đối không triển khai cơ chế xác thực riêng.

> [!WARNING]
> **Khả Năng Chịu Lỗi của Telemetry Producer (Non-Failing Telemetry):**
> Việc đẩy sự kiện viễn thám vào Kafka được thực hiện qua `BackgroundTasks` sau khi worker đã hoàn tất dự đoán. Nếu kết nối tới Kafka bị gián đoạn hoặc gửi event thất bại, Model Server sẽ ghi nhận log lỗi cảnh báo (`ERROR`) nhưng **tuyệt đối không làm gián đoạn hay trả về mã lỗi 500 cho yêu cầu suy luận của người dùng**.

> [!TIP]
> **Định Tuyến Đa Nền Tảng (Environment-Aware Routing):**
> Hàm `resolve_worker_url` tự động phân tích cấu trúc triển khai của mô hình:
> - Trong Docker Compose, worker URL sử dụng cổng và tên dịch vụ Docker container nội bộ.
> - Trong Kubernetes, worker URL tự động chuyển đổi sang định dạng FQDN của K8s CoreDNS (`<service-name>.<namespace>.svc.cluster.local:<port>`). Nếu worker pod chưa sẵn sàng hoặc không tồn tại, Gateway sẽ trả về mã `503 Service Unavailable` rõ ràng.

> [!NOTE]
> **Bộ Đệm và Invalidation Cache:**
> Khi thông tin phiên bản mô hình hoặc cấu hình triển khai được cập nhật tại Control Plane, cache trên Redis sẽ tự động bị xóa (invalidation). Nếu kết nối tới Redis bị gián đoạn, Gateway sẽ fallback an toàn về truy vấn PostgreSQL trực tiếp.
