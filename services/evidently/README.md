# Evidently — Động Cơ Phân Tích & Giám Sát Trôi Dạt Dữ Liệu (Drift Detection Engine)

Thư mục `services/evidently/` chứa mã nguồn của **Evidently Service**, một Worker Runner chuyên biệt thực hiện việc phân tích trôi dạt dữ liệu (Data Drift) và trôi dạt dự đoán (Target/Prediction Drift). Dịch vụ dựa trên nền tảng thư viện **Evidently AI** (phiên bản ổn định 0.4.x), đóng vai trò then chốt trong việc giám sát chất lượng mô hình sau triển khai và là ngòi nổ kích hoạt quy trình Tái huấn luyện Liên tục (Continuous Training - CT).

---

## 1. Giới thiệu

### 1.1. Vai trò trong hệ thống

Sau khi một mô hình học máy được triển khai lên môi trường sản xuất, phân phối của dữ liệu đầu vào thực tế thường có xu hướng biến đổi theo thời gian so với dữ liệu huấn luyện ban đầu (hiện tượng Data Drift), dẫn đến suy giảm độ chính xác của mô hình. Evidently Service giải quyết vấn đề này với các nhiệm vụ cốt lõi:

1. **So sánh Phân phối Thống kê Đa biến (Statistical Drift Analysis):**
   - Tải tập dữ liệu cơ sở chuẩn (**Reference Dataset** tải từ S3 qua Presigned URL, thường là tập dữ liệu huấn luyện hoặc tập kiểm thử được lưu trữ lúc huấn luyện mô hình).
   - Truy vấn tập dữ liệu suy luận thực tế phát sinh trên môi trường sản xuất (**Current Production Data** lưu trữ trong bảng `production_predictionrecord` của cơ sở dữ liệu PostgreSQL).
   - Tự động áp dụng các phép kiểm định thống kê phù hợp cho từng loại đặc trưng:
     - **Biến liên tục (Numerical Features):** Kolmogorov-Smirnov Test (K-S test) hoặc Wasserstein Distance.
     - **Biến phân loại (Categorical Features):** Chi-Square Test hoặc Jensen-Shannon Divergence.
2. **Tự động Đối chiếu Cấu trúc Cột (Signature & Column Mapping):**
   - Đọc thông tin chữ ký mô hình (MLflow Model Signature) hoặc phân tích cấu trúc trường `features` (dạng `JSONB` trong database) để tự động ánh xạ các cột đặc trưng (`ColumnMapping`).
   - Tự động làm phẳng (flatten) dữ liệu JSON lồng nhau và loại bỏ các cột không liên quan trước khi đưa vào thuật toán phân tích.
3. **Sinh Báo cáo Toàn diện Đa Định dạng (Multi-Format Reporting):**
   - **Báo cáo HTML Tương tác (`report.html`):** Chứa các biểu đồ phân phối trực quan, bảng thống kê p-value chi tiết của từng đặc trưng để người dùng xem trực tiếp trên Web Dashboard.
   - **Báo cáo Chi tiết JSON (`report.json`):** Chứa toàn bộ thông số toán học và kết quả kiểm định chi tiết.
   - **Báo cáo Tóm tắt JSON (`summary.json`):** Tóm tắt nhanh các chỉ số cốt lõi: tổng số đặc trưng, số lượng đặc trưng bị drift, tỷ lệ trôi dạt thực tế (`drift_share`), và kết luận boolean xem drift có vượt ngưỡng cho phép (`DRIFT_THRESHOLD`, ví dụ: 0.6) hay không.
4. **Cầu nối Tự động Kích hoạt Continuous Training (CT Trigger):**
   - Sau khi hoàn thành phân tích và đẩy 3 file báo cáo lên S3 qua Presigned URLs, Evidently gửi Webhook Callback báo cáo kết quả về Control Plane.
   - Nếu tỷ lệ drift vượt ngưỡng an toàn đã cấu hình trong `DriftMonitor`, module `apps.ct` của Control Plane sẽ tự động tạo một `TrainingJob` mới để huấn luyện lại mô hình với dữ liệu cập nhật.

```
+------------------+                   +------------------------------------+
|  AWS S3 Storage  |                   |        PostgreSQL Database         |
| (Reference Data) |                   |  (Bảng: production_prediction)     |
+------------------+                   +------------------------------------+
         │                                               │
         │ (Tải qua Presigned GET)                       │ (Truy vấn qua DB_HOST_RO)
         ▼                                               ▼
+---------------------------------------------------------------------------+
|                              EVIDENTLY RUNNER                             |
|                                                                           |
|  1. Đọc ngữ cảnh: TENANT_ID, PROJECT_ID, MODEL_VERSION_ID, DRIFT_RUN_ID   |
|  2. Tiền xử lý dữ liệu: Flatten JSONB features, kiểm tra min samples      |
|  3. Thiết lập ColumnMapping dựa trên MLmodel Signature                    |
|  4. Thực thi Evidently AI: Report([DataDriftPreset()])                    |
|  5. Tính toán p-value, drift share và so sánh với DRIFT_THRESHOLD         |
|  6. Sinh 3 định dạng: report.html, report.json, summary.json              |
|  7. Upload cả 3 file lên S3 qua Presigned PUT URLs                        |
+---------------------------------------------------------------------------+
                                       │
                                       │ POST /internal/webhooks/drift-runs/<run_id>/
                                       ▼
+---------------------------------------------------------------------------+
|                               CONTROL PLANE                               |
|  - Lưu trữ kết quả phiên phân tích DriftRun vào PostgreSQL                |
|  - Nếu drift vượt ngưỡng: Kích hoạt Continuous Training (CT) Pipeline     |
+---------------------------------------------------------------------------+
```

---

### 1.2. Các thành phần chính

| Module / File | Trách nhiệm chính |
|---|---|
| **`src/main.py`** | Entrypoint mỏng khởi chạy ứng dụng và xử lý mã lỗi thoát an toàn. |
| **`src/application.py`** | Điều phối toàn bộ vòng đời phiên phân tích trôi dạt (`main`): kiểm tra tham số môi trường, phối hợp các module tải dữ liệu, phân tích, xuất báo cáo và gửi webhook callback. |
| **`src/data.py`** | Tầng truy xuất và chuẩn hóa dữ liệu: tải dataset tham chiếu từ S3 (hỗ trợ CSV và Parquet), truy vấn bản ghi suy luận từ cơ sở dữ liệu PostgreSQL, làm phẳng cấu trúc `features` JSONB và đính kèm cột `prediction`. |
| **`src/analysis.py`** | Nhân phân tích thống kê: cấu hình `ColumnMapping`, áp dụng `DataDriftPreset` của Evidently AI, tính toán số lượng đặc trưng trôi dạt và tỷ lệ `drift_share`. |
| **`src/reporting.py`** | Tầng sinh và xuất bản báo cáo: tạo file HTML tương tác, xuất dữ liệu JSON chi tiết và tóm tắt JSON, thực hiện upload lên S3 qua Presigned PUT URLs. |
| **`src/config.py`** | Quản lý các biến môi trường, ngưỡng `DRIFT_THRESHOLD` (mặc định: `0.6`), giới hạn số lượng mẫu (`MIN_SAMPLES`, `MAX_SAMPLES`). |
| **`src/logging_utils.py`** | Bộ quản lý log chuyên biệt: hỗ trợ stream nhật ký chạy trực tiếp vào Redis (`drift_logs:{run_id}`) và ghi nhật ký có cấu trúc ra stdout. |

---

### 1.3. Luồng hoạt động

1. **Khởi động và Xác thực Tham số Môi trường:**
   - Dịch vụ khởi động, đọc bộ 4 định danh: `TENANT_ID`, `PROJECT_ID`, `MODEL_VERSION_ID`, `DRIFT_RUN_ID`.
   - Kết nối tới Redis để sẵn sàng stream log thời gian thực (`drift_logs:{run_id}`).
2. **Nạp và Chuẩn bị Dữ liệu:**
   - **Dữ liệu tham chiếu (Reference Data):** Tải file từ `REFERENCE_DATA_URL` (hỗ trợ CSV/Parquet) về thư mục tạm, chuyển đổi thành Pandas DataFrame.
   - **Dữ liệu sản xuất (Current Data):** Kết nối tới PostgreSQL thông qua tài khoản Read-Only (`DB_HOST_RO`), truy vấn tối đa `MAX_SAMPLES` bản ghi suy luận gần nhất của `model_version_id`.
3. **Kiểm tra Điều kiện Tiên quyết (Guard Checks):**
   - Nếu số lượng bản ghi sản xuất thu thập được nhỏ hơn `MIN_SAMPLES` (mặc định 100 mẫu), hệ thống đánh dấu trạng thái `insufficient_samples` một cách có kiểm soát và báo cáo về Control Plane, không làm sập tiến trình.
   - Làm phẳng các cột đặc trưng JSONB và đối chiếu danh sách cột dùng chung giữa hai tập dữ liệu.
4. **Thực thi Phân tích Trôi dạt:**
   - Khởi tạo báo cáo Evidently: `Report(metrics=[DataDriftPreset()])`.
   - Chạy tính toán phân phối và kiểm định giả thuyết thống kê giữa Reference Data và Current Data.
   - Trích xuất số lượng cột bị drift và tính `drift_share = drift_features / total_features`.
5. **Xuất bản Báo cáo & Upload S3:**
   - Xuất file HTML trực quan: `report.save_html()`.
   - Xuất file JSON chi tiết: `report.json()`.
   - Xuất file JSON tóm tắt chứa các thông số:
     ```json
     {
       "drift_detected": true,
       "drift_share": 0.75,
       "drift_threshold": 0.6,
       "number_of_features": 20,
       "number_of_drifted_features": 15,
       "reference_samples": 5000,
       "current_samples": 1200
     }
     ```
   - Tải cả 3 file lên S3 thông qua các URL: `HTML_UPLOAD_URL`, `REPORT_JSON_UPLOAD_URL`, `SUMMARY_JSON_UPLOAD_URL`.
6. **Báo cáo Trạng thái về Control Plane:**
   - Gửi Webhook callback tới `CONTROL_PLANE_WEBHOOK_URL` kèm thông tin tóm tắt và header `Idempotency-Key`.
   - Control Plane cập nhật trạng thái `DriftRun` thành `COMPLETED` và lưu các chỉ số drift vào database để hiển thị trên dashboard.

---

## 2. Cấu trúc cây thư mục

```text
services/evidently/
├── Dockerfile                         # Khai báo image runtime cho Evidently worker
├── requirements.txt                   # Danh sách thư viện (evidently, pandas, sqlalchemy)
├── src/                               # Toàn bộ mã nguồn nghiệp vụ
│   ├── __init__.py
│   ├── main.py                        # Entrypoint mỏng của tiến trình
│   ├── application.py                 # Điều phối quy trình phân tích và báo cáo
│   ├── analysis.py                    # Khởi tạo Evidently DataDriftPreset và tính toán
│   ├── data.py                        # Truy vấn dữ liệu S3/PostgreSQL và chuẩn hóa JSONB
│   ├── reporting.py                   # Sinh file HTML/JSON và upload lên S3
│   ├── config.py                      # Quản lý ngưỡng drift và cấu hình số lượng mẫu
│   `-- logging_utils.py               # Quản lý stream log vào Redis và format stdout
`-- tests/                             # Bộ kiểm thử tự động
    ├── __init__.py
    ├── conftest.py                    # Fixtures giả lập DataFrame và Mock DB
    ├── test_evidently.py              # Kiểm thử tính toán drift và sinh báo cáo
    ├── test_logging.py                # Kiểm thử cấu hình logger
    `-- test_logging_utils.py          # Kiểm thử Redis stream log
```

---

## 3. Hướng dẫn khởi chạy và các lệnh cần thiết

### 3.1. Chạy thử nghiệm qua Docker Container

Evidently là một tác vụ chạy theo lịch trình hoặc sự kiện (Scheduled / On-Demand Task) do Control Plane kích hoạt. Bạn có thể chạy thử nghiệm phân tích bằng lệnh Docker:

```bash
docker run --rm \
  -e DRIFT_RUN_ID="019488a0-3000-7000-8000-000000000001" \
  -e PROJECT_ID="019488a0-3000-7000-8000-000000000002" \
  -e MODEL_VERSION_ID="019488a0-3000-7000-8000-000000000003" \
  -e REFERENCE_DATA_URL="https://your-s3-presigned-url/reference.csv" \
  -e HTML_UPLOAD_URL="https://your-s3-presigned-url/report.html" \
  -e REPORT_JSON_UPLOAD_URL="https://your-s3-presigned-url/report.json" \
  -e SUMMARY_JSON_UPLOAD_URL="https://your-s3-presigned-url/summary.json" \
  -e CONTROL_PLANE_WEBHOOK_URL="http://control-plane:8000/internal/webhooks/drift-runs/019488a0-3000-7000-8000-000000000001/" \
  -e CONTROL_PLANE_WEBHOOK_SECRET="local-webhook-secret" \
  -e DB_USER="postgres" \
  -e DB_PASSWORD="postgres" \
  -e DB_HOST_RO="postgres" \
  -e DB_NAME="mlops_paas_db" \
  -e DRIFT_THRESHOLD="0.6" \
  mlops-paas-evidently:latest
```

### 3.2. Chạy thử nghiệm trực tiếp trên máy chủ / Virtualenv

#### Bước 1: Chuẩn bị môi trường ảo
```bash
cd services/evidently
python -m venv .venv
# Trên Windows:
.venv\Scripts\Activate.ps1
# Trên Linux/macOS:
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

#### Bước 2: Thiết lập cấu hình và chạy thử
```bash
export DRIFT_RUN_ID=test-drift-run-uuid
export PROJECT_ID=test-project-uuid
export MODEL_VERSION_ID=test-model-version-uuid
export DRIFT_THRESHOLD=0.6

# Chạy tiến trình phân tích
python -m src.main
```

---

### 3.3. Các biến môi trường quan trọng

| Tên biến | Bắt buộc | Mô tả chức năng |
|---|---|---|
| `DRIFT_RUN_ID` | Có | UUID duy nhất xác định phiên phân tích trôi dạt. |
| `PROJECT_ID` | Có | UUID của dự án sở hữu mô hình. |
| `MODEL_VERSION_ID` | Có | UUID của phiên bản mô hình cần đánh giá trôi dạt. |
| `TENANT_ID` | Có | UUID xác định tenant sở hữu. |
| `REFERENCE_DATA_URL` | Có | Presigned GET URL tải tập dữ liệu cơ sở tham chiếu từ S3. |
| `HTML_UPLOAD_URL` | Có | Presigned PUT URL tải file báo cáo HTML lên S3. |
| `REPORT_JSON_UPLOAD_URL` | Có | Presigned PUT URL tải file kết quả JSON chi tiết lên S3. |
| `SUMMARY_JSON_UPLOAD_URL`| Có | Presigned PUT URL tải file tóm tắt chỉ số JSON lên S3. |
| `CONTROL_PLANE_WEBHOOK_URL`| Có | URL nội bộ của Control Plane tiếp nhận kết quả phân tích. |
| `CONTROL_PLANE_WEBHOOK_SECRET`| Có | Khóa bí mật Bearer token xác thực webhook callback. |
| `DRIFT_THRESHOLD` | Không | Ngưỡng tỷ lệ đặc trưng bị drift để cảnh báo (mặc định: `0.6`). |
| `MIN_SAMPLES` | Không | Số lượng mẫu sản xuất tối thiểu để phân tích (mặc định: `100`). |
| `MAX_SAMPLES` | Không | Số lượng mẫu sản xuất tối đa được truy vấn (mặc định: `100000`). |
| `DB_HOST_RO` | Có | Địa chỉ máy chủ PostgreSQL Read-Only để đọc dữ liệu sản xuất. |

---

### 3.4. Kiểm tra chất lượng & Chạy Unit Test (Quality Gates)

```bash
# 1. Kiểm tra Linting với Ruff
python -m ruff check .

# 2. Chạy toàn bộ bộ kiểm thử tự động với Pytest
python -m pytest --cov=src --cov-report=term-missing
```

---

## 4. Các chú ý quan trọng (Architectural Constraints & Caveats)

> [!IMPORTANT]
> **Bộ Bốn Định Danh Bắt Buộc (Identity Invariant):**
> Mỗi phiên phân tích Evidently bắt buộc phải có đầy đủ 4 định danh trong ngữ cảnh thực thi: `TENANT_ID`, `PROJECT_ID`, `MODEL_VERSION_ID`, và `DRIFT_RUN_ID`.

> [!WARNING]
> **Sử Dụng Kết Nối Đọc Cơ Sở Dữ Liệu (Read-Only Database Access):**
> Evidently chỉ được phép kết nối vào PostgreSQL thông qua biến `DB_HOST_RO` với quyền truy cập chỉ đọc (`SELECT`). **Tuyệt đối không cấp quyền ghi hoặc thực thi các câu lệnh thay đổi dữ liệu** nhằm bảo vệ cơ sở dữ liệu chính không bị ảnh hưởng hiệu năng khi thực hiện các câu truy vấn quét khối lượng lớn bản ghi sản xuất.

> [!CAUTION]
> **Xử Lý Thiếu Mẫu An Toàn (Controlled Insufficient Samples):**
> Nếu lượng dữ liệu sản xuất tích lũy chưa đạt `MIN_SAMPLES`, Evidently sẽ coi đây là một kết quả phân tích có kiểm soát và báo cáo trạng thái `insufficient_samples` về Control Plane thay vì quăng lỗi ngoại lệ làm sập container.

> [!TIP]
> **Tích Hợp Tự Động Hóa Continuous Training (CT):**
> Khi tỷ lệ `drift_share` vượt quá `DRIFT_THRESHOLD`, Webhook callback sẽ mang cờ `drift_detected: true`. Control Plane sẽ dựa vào cờ này và cấu hình của `DriftMonitor` để tự động kích hoạt một `TrainingJob` mới, thực hiện tải dữ liệu sản xuất đã tích lũy và tiến hành tái huấn luyện mô hình một cách hoàn toàn tự động.
