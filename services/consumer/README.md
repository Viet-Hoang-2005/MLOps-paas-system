# Consumer — Worker Thu Thập Dữ Liệu Sản Xuất & Điều Phối Drift Outbox

Thư mục `services/consumer/` chứa mã nguồn của **Consumer Service**, một Background Worker hiệu năng cao chạy liên tục giữa hệ thống hàng đợi phân tán (Redpanda / Kafka) và cơ sở dữ liệu PostgreSQL. Dịch vụ chịu trách nhiệm thu thập toàn bộ dữ liệu suy luận thực tế (Production Inference Telemetry), lưu trữ bền vững và điều phối tín hiệu phát hiện trôi dạt dữ liệu (Automatic Drift Signals) tới Control Plane.

---

## 1. Giới thiệu

### 1.1. Vai trò trong hệ thống

Trong kiến trúc MLOps PaaS, Consumer đóng vai trò là **Đầu mối tiếp nhận dữ liệu sản xuất (Production Data Ingestion Pipeline)** và **Cầu nối kích hoạt giám sát chất lượng mô hình (Drift Trigger Gateway)**:

1. **Thu thập dữ liệu suy luận bất đồng bộ (Asynchronous Telemetry Ingestion):**
   - Khi các mô hình phục vụ suy luận (`model-server` / runtime workers) trả về kết quả dự đoán thành công cho người dùng, một sự kiện chứa payload (features, prediction, model version, timestamp, latency) sẽ được đẩy vào topic Kafka `mlops_paas_production_data`.
   - Consumer liên tục lắng nghe và tiêu thụ các sự kiện này ở chế độ nền mà không làm ảnh hưởng đến độ trễ (latency) của luồng dự đoán trực tiếp.
2. **Kỹ thuật gom cụm dữ liệu vi mô (Micro-Batching Engine):**
   - Thay vì thực hiện ghi đơn lẻ từng dòng vào database (gây nghẽn I/O), Consumer gom các bản ghi thành từng batch theo từng Kafka partition và ghi hàng loạt (Bulk Insert qua Pandas / SQLAlchemy) khi đạt kích thước batch tối đa (`KAFKA_BATCH_SIZE`) hoặc vượt thời gian chờ nhàn rỗi (`idle timeout`).
3. **Mô hình Transactional Outbox & Tín hiệu Drift Tự động:**
   - Cùng trong một Transaction PostgreSQL ghi dữ liệu dự đoán, Consumer tự động sinh các bản ghi tín hiệu trôi dạt vào bảng outbox (`observability_eventoutbox`) cho từng phiên bản mô hình có dữ liệu mới.
   - Một tiến trình dispatcher riêng biệt trong Consumer sẽ quét outbox, thực hiện gửi Webhook sang Control Plane với cơ chế retry và exponential backoff mà không làm gián đoạn hay chặn luồng đọc Kafka chính.
4. **Cam kết phân phối dữ liệu At-Least-Once & Xử lý Idempotency:**
   - Offset của Kafka chỉ được commit đồng bộ SAU KHI dữ liệu đã được ghi bền vững vào PostgreSQL.
   - Mọi bản ghi đều sử dụng UUID làm khóa chính, khi xảy ra sự cố và cần replay dữ liệu, câu lệnh SQL sử dụng `ON CONFLICT (id) DO NOTHING` để loại bỏ nguy cơ trùng lặp bản ghi.

```
+------------------+
|   Model Server   | (Sau khi suy luận thành công)
+------------------+
         |
         | (Publish event JSON)
         v
+-------------------------------------------------------------+
|               Redpanda / Kafka Cluster                      |
|          Topic: mlops_paas_production_data                  |
+-------------------------------------------------------------+
         |
         | (Subscribe & Poll records)
         v
+-------------------------------------------------------------+
|                      CONSUMER WORKER                        |
|                                                             |
|  +-------------------------------------------------------+  |
|  |             Kafka Runtime (Main Thread)               |  |
|  |  - Micro-batching theo partition                      |  |
|  |  - Chuẩn hóa timestamp UTC, parse JSONB features      |  |
|  |  - Ghi đồng thời dữ liệu dự đoán & outbox signal      |  |
|  |  - Commit Kafka Offset sau khi DB commit thành công   |  |
|  +-------------------------------------------------------+  |
|                            │                                |
|        (Ghi vào cùng DB    │ (Claim signal & retry HTTP)    |
|         Transaction)       ▼                                |
|  +-------------------------------------------------------+  |
|  |           Automatic Drift Outbox Dispatcher           |  |
|  |                  (Background Thread)                  |  |
|  +-------------------------------------------------------+  |
+-------------------------------------------------------------+
         │                                   │
         │ (Bulk INSERT)                     │ (POST /internal/webhooks/automatic-drift/)
         v                                   v
+------------------+                +------------------+
|    PostgreSQL    |                |  Control Plane   |
| (Schema SSOT)    |                | (Drift Checker)  |
+------------------+                +------------------+
```

---

### 1.2. Các thành phần chính

Mã nguồn của Consumer được tổ chức phân tách rõ ràng theo từng trách nhiệm:

| Thành phần / File | Trách nhiệm chính |
|---|---|
| **`src/main.py`** | Entrypoint mỏng (Thin Process Entrypoint) khởi động quy trình, cấu hình logging chuẩn trước khi nạp các module thực thi. |
| **`src/kafka_runtime.py`** | Trình quản trị vòng lặp Kafka: khởi tạo consumer, poll tin nhắn, phân loại buffer theo Partition, quản lý commit offset chính xác và giám sát luồng Outbox Dispatcher. |
| **`src/batching.py`** | Chuyển đổi dữ liệu từ sự kiện Kafka sang cấu trúc bảng: chuẩn hóa thời gian UTC, đóng gói trường `features` dạng `JSONB` linh hoạt (hỗ trợ mọi định dạng model), và tạo các payload tín hiệu drift. |
| **`src/database.py`** | Tầng tương tác PostgreSQL: khởi tạo Connection Pool (SQLAlchemy + psycopg2), kiểm tra trạng thái bảng (`init_db`), thực thi bulk insert với `ON CONFLICT DO NOTHING`, và cung cấp các hàm thao tác với bảng outbox (`claim`, `mark_published`, `reschedule`). |
| **`src/drift_outbox.py`** | Luồng xử lý Outbox chạy nền: định kỳ quét các tín hiệu chưa gửi (`claim_automatic_drift_signals` kèm lease lock), gọi Webhook nội bộ sang Control Plane có chữ ký xác thực Bearer Secret và `Idempotency-Key`, tính toán thời gian retry lũy thừa (exponential backoff). |
| **`src/models.py`** | Khai báo các Dataclass mô tả cấu trúc bản ghi Kafka (`KafkaRecord`), trạng thái thử lại của Partition (`RetryState`), và custom exceptions (`KafkaRecordProcessingError`). |
| **`src/logging_utils.py`** | Chuẩn hóa hệ thống log của service (định dạng Console hoặc JSON một dòng), tự động tính toán và xuất bản báo cáo tóm tắt số liệu (Summary: Kafka Poll, DB Persistence, Offset Commit, Signal Delivery) định kỳ mỗi 60 giây. |

---

### 1.3. Luồng hoạt động

#### Luồng 1: Xử lý Gom cụm và Ghi Dữ liệu Dự đoán (Ingestion & Micro-Batching)
1. **Poll tin nhắn:** `kafka_runtime` liên tục gọi `consumer.poll()` từ Redpanda.
2. **Phân bổ Buffer:** Mỗi bản ghi hợp lệ được đưa vào hàng đợi đệm (buffer) tương ứng với cặp `(topic, partition)`.
3. **Kiểm tra điều kiện xả đệm (Flush Condition):**
   - Đạt số lượng bản ghi tối đa (`len(buffer) >= KAFKA_BATCH_SIZE`), **hoặc**
   - Hết thời gian chờ nhàn rỗi (idle timeout), **hoặc**
   - Nhận tín hiệu dừng dịch vụ (`SIGTERM`/`SIGINT`).
4. **Mở Transaction ghi cơ sở dữ liệu:**
   - Chuyển buffer thành DataFrame và thực hiện `INSERT INTO control_plane.production_predictionrecord ... ON CONFLICT (id) DO NOTHING`.
   - Trong cùng transaction, tạo các bản ghi tín hiệu trôi dạt `INSERT INTO control_plane.observability_eventoutbox ... ON CONFLICT (idempotency_key) DO NOTHING`.
5. **Đồng bộ Offset (Commit Offset):**
   - Sau khi transaction cơ sở dữ liệu commit thành công, Consumer thực hiện commit offset đồng bộ (`consumer.commit(asynchronous=False)`) tới vị trí bản ghi cuối cùng + 1.
   - Chỉ giải phóng bộ nhớ đệm (clear buffer) khi offset đã được Kafka xác nhận.
6. **Xử lý lỗi cấp Partition (Partition-level Isolation):**
   - Nếu gặp lỗi kết nối DB hoặc lỗi commit offset, Consumer chỉ tạm dừng (pause) riêng partition bị ảnh hưởng và thực hiện backoff retry (`KAFKA_DB_RETRY_INITIAL_SECONDS` $\rightarrow$ `KAFKA_DB_RETRY_MAX_SECONDS`), các partition khác vẫn tiếp tục tiêu thụ bình thường.

#### Luồng 2: Điều phối Tín hiệu Drift Bất đồng bộ (Outbox Dispatcher)
1. **Khởi động luồng nền:** Khi Consumer chạy, một thread độc lập mang tên `automatic-drift-outbox` được kích hoạt.
2. **Khóa và lấy tín hiệu (Lease Claim):** Định kỳ mỗi `AUTOMATIC_DRIFT_OUTBOX_POLL_SECONDS` (mặc định 5s), thread gọi DB để claim tối đa 50 tín hiệu pending và gắn thời gian khóa `lease_seconds = 60s` (tránh việc nhiều replica cùng gửi một tín hiệu).
3. **Gửi Webhook sang Control Plane:**
   - Gửi HTTP `POST` tới `CONTROL_PLANE_AUTOMATIC_DRIFT_WEBHOOK_URL`.
   - Header chứa `Authorization: Bearer <CONTROL_PLANE_WEBHOOK_SECRET>` và `Idempotency-Key`.
4. **Xử lý phản hồi:**
   - **Thành công (Mã 2xx):** Đánh dấu trạng thái outbox là `published` và xóa khỏi hàng đợi chờ.
   - **Thất bại hoặc Timeout:** Tăng biến `attempts`, tính toán thời gian thử lại kế tiếp (exponential backoff) và cập nhật lại thời điểm `available_at` trong DB.

---

## 2. Cấu trúc cây thư mục

```text
services/consumer/
├── Dockerfile                         # Khai báo container runtime cho Consumer
├── requirements.txt                   # Danh sách thư viện Python phụ thuộc
├── src/                               # Toàn bộ mã nguồn nghiệp vụ
│   ├── __init__.py
│   ├── main.py                        # Entrypoint mỏng khởi động ứng dụng
│   ├── kafka_runtime.py               # Quản trị vòng lặp Kafka, buffer và offset commit
│   ├── batching.py                    # Chuyển đổi dữ liệu bản ghi và logic micro-batching
│   ├── database.py                    # Tầng kết nối và thao tác dữ liệu PostgreSQL
│   ├── drift_outbox.py                # Worker thread quét và gửi tín hiệu drift webhook
│   ├── models.py                      # Định nghĩa Data models và cấu trúc dữ liệu nội bộ
│   `-- logging_utils.py               # Chuẩn hóa logging và định kỳ xuất summary metrics
`-- tests/                             # Bộ kiểm thử đơn vị độc lập (Mock DB & Broker)
    ├── __init__.py
    ├── test_consumer.py               # Kiểm thử vòng lặp tiêu thụ và micro-batching
    ├── test_database.py               # Kiểm thử các câu lệnh SQL và logic outbox persistence
    ├── test_drift_outbox.py           # Kiểm thử luồng gửi webhook và cơ chế exponential retry
    ├── test_logging.py                # Kiểm thử định dạng log Console/JSON
    `-- test_logging_utils.py          # Kiểm thử cơ chế gom số liệu Summary metrics
```

---

## 3. Hướng dẫn khởi chạy và các lệnh cần thiết

### 3.1. Khởi chạy bằng Docker Compose (Môi trường phát triển cục bộ)

Consumer được cấu hình sẵn trong `docker-compose.yml` để chạy cùng với PostgreSQL, Redpanda và Control Plane:

```bash
# Khởi động Consumer cùng các dịch vụ phụ thuộc
docker compose up -d consumer

# Theo dõi nhật ký log trực tiếp của Consumer
docker compose logs -f consumer
```

### 3.2. Khởi chạy trực tiếp trên máy chủ / Virtualenv (Không dùng Docker)

#### Bước 1: Chuẩn bị môi trường ảo
```bash
# Chuyển vào thư mục service
cd services/consumer

# Tạo và kích hoạt môi trường ảo Python 3.12+
python -m venv .venv
# Trên Windows:
.venv\Scripts\Activate.ps1
# Trên Linux/macOS:
source .venv/bin/activate

# Cài đặt thư viện phụ thuộc
pip install --upgrade pip
pip install -r requirements.txt
```

#### Bước 2: Thiết lập biến môi trường
Tạo file `.env` hoặc cấu hình trực tiếp trên terminal:
```bash
export REDPANDA_BROKERS=localhost:19092
export KAFKA_TOPIC=mlops_paas_production_data
export KAFKA_BATCH_SIZE=500
export DB_USER=postgres
export DB_PASSWORD=postgres
export DB_HOST_RW=localhost
export DB_HOST_RO=localhost
export DB_PORT=5432
export DB_NAME=mlops_paas_db
export DB_SCHEMA=control_plane
export CONTROL_PLANE_AUTOMATIC_DRIFT_WEBHOOK_URL=http://localhost:8000/internal/webhooks/automatic-drift/
export CONTROL_PLANE_WEBHOOK_SECRET=local-webhook-secret
```

#### Bước 3: Khởi chạy Worker
```bash
# Chạy worker thông qua process entrypoint chuẩn
python -m src.main
```

---

### 3.3. Các biến môi trường quan trọng

| Tên biến | Giá trị mặc định | Mô tả chức năng |
|---|---|---|
| `REDPANDA_BROKERS` | `localhost:19092` | Địa chỉ máy chủ hàng đợi Redpanda / Kafka. |
| `KAFKA_TOPIC` | `mlops_paas_production_data` | Topic lắng nghe các sự kiện suy luận từ Model Server. |
| `KAFKA_BATCH_SIZE` | `500` | Số lượng bản ghi tối đa trong một đợt ghi (micro-batch) của mỗi partition. |
| `KAFKA_DB_RETRY_INITIAL_SECONDS` | `5` | Thời gian backoff ban đầu khi gặp lỗi ghi DB hoặc lỗi commit offset. |
| `KAFKA_DB_RETRY_MAX_SECONDS` | `60` | Thời gian backoff tối đa cho mỗi partition bị lỗi. |
| `CONTROL_PLANE_AUTOMATIC_DRIFT_WEBHOOK_URL` | `""` | Địa chỉ Webhook nội bộ của Control Plane tiếp nhận tín hiệu drift. |
| `CONTROL_PLANE_WEBHOOK_SECRET` | `""` | Khóa bí mật Bearer Token để xác thực với Control Plane. |
| `AUTOMATIC_DRIFT_OUTBOX_POLL_SECONDS` | `5` | Chu kỳ quét bảng outbox của thread dispatcher (giây). |
| `AUTOMATIC_DRIFT_OUTBOX_BATCH_SIZE` | `50` | Số lượng tín hiệu tối đa được claim trong mỗi lần quét outbox. |
| `AUTOMATIC_DRIFT_OUTBOX_LEASE_SECONDS` | `60` | Thời gian khóa (lease lock) một tín hiệu để ngăn các replica khác gửi trùng. |
| `AUTOMATIC_DRIFT_OUTBOX_RETRY_INITIAL_SECONDS` | `5` | Thời gian chờ thử lại ban đầu khi webhook gửi lỗi (giây). |
| `AUTOMATIC_DRIFT_OUTBOX_RETRY_MAX_SECONDS` | `300` | Thời gian chờ thử lại tối đa (exponential backoff trần). |
| `DB_HOST_RW` / `DB_HOST_RO` | `postgres` | Địa chỉ PostgreSQL cho kết nối Ghi (Read-Write) và Đọc (Read-Only). |

---

### 3.4. Kiểm tra chất lượng & Chạy Unit Test (Quality Gates)

Consumer được thiết kế để kiểm thử độc lập 100% không yêu cầu kết nối thật tới Kafka hay PostgreSQL:

```bash
# 1. Kiểm tra quy chuẩn code với Ruff
python -m ruff check .

# 2. Chạy toàn bộ bộ kiểm thử tự động với Pytest và tính độ bao phủ (Coverage)
python -m pytest --cov=src --cov-report=term-missing
```

---

## 4. Các chú ý quan trọng (Operational Constraints & Caveats)

> [!IMPORTANT]
> **Consumer Không Sở Hữu Schema (No DDL Execution):**
> Consumer tuyệt đối **không chạy lệnh tạo bảng (`CREATE TABLE`) hay sửa đổi cấu trúc DDL**. Bảng `production_predictionrecord` và `observability_eventoutbox` hoàn toàn do migrations của Control Plane khởi tạo và sở hữu. Hàm `init_db()` của Consumer chỉ kiểm tra sự tồn tại của các bảng này, nếu bảng chưa có thì tiến trình sẽ báo lỗi và dừng lại an toàn để chờ Control Plane migrate xong.

> [!WARNING]
> **Không Chặn Luồng Kafka (Non-Blocking Ingestion Pipeline):**
> Luồng gửi webhook báo cáo drift sang Control Plane được tách rời hoàn toàn vào một background thread riêng biệt (`automatic-drift-outbox`). Lỗi mạng hoặc sự chậm trễ từ phía Control Plane **tuyệt đối không được làm nghẽn (block) vòng lặp poll và commit offset của Kafka**.

> [!CAUTION]
> **Đồng Bộ Offset Sau Ghi DB (Commit-After-Persist):**
> Để đảm bảo tính toàn vẹn dữ liệu, Consumer chỉ commit Kafka offset khi giao dịch `INSERT` dữ liệu vào PostgreSQL đã thành công 100%. Nếu cơ sở dữ liệu gặp sự cố, Consumer sẽ tạm dừng partition đó và thử lại, không commit offset để tránh mất mát dữ liệu (Data Loss).

> [!TIP]
> **Khả Năng Phục Hồi Tự Động (Process Crash Resilience):**
> Nếu thread `automatic-drift-outbox` gặp lỗi ngoại lệ nghiêm trọng không thể tự phục hồi, hàm `ensure_outbox_dispatcher_running()` trong luồng chính sẽ chủ động raise `RuntimeError` để thoát process, giúp Docker hoặc Kubernetes Pod Restart Policy tự động tạo mới lại container.
