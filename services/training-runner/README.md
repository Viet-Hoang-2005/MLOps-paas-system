# Training Runner — Thực Thi Huấn Luyện Mô Hình Học Máy (Training Execution Engine)

Thư mục `services/training-runner/` chứa mã nguồn của **Training Runner Service**, một Worker Container độc lập chuyên biệt hóa cho việc thực thi các tác vụ huấn luyện mô hình học máy (Machine Learning & Deep Learning Training Jobs). Dịch vụ chạy trong môi trường cô lập (Sandbox) để thực thi mã nguồn tùy biến của người dùng một cách an toàn, thu thập siêu dữ liệu huấn luyện, stream logs thời gian thực và đóng gói kết quả đầu ra.

---

## 1. Giới thiệu

### 1.1. Vai trò trong hệ thống

Trong kiến trúc MLOps PaaS, Training Runner là thành phần trực tiếp thi hành các bài toán huấn luyện được giao bởi Control Plane (thông qua Docker Container ở môi trường local hoặc Kubernetes `PyTorchJob` / Argo Workflow có gắn GPU trên Production):

1. **Môi trường Thực thi Cô lập Cho Tác vụ Người dùng (Untrusted Workload Sandbox):**
   - Mã nguồn huấn luyện do người dùng tải lên được hệ thống xếp vào diện "không tin cậy" (Untrusted Tenant Code). Training Runner chạy trong container cách ly, **tuyệt đối không nắm giữ AWS credentials, mật khẩu cơ sở dữ liệu hệ thống, hoặc quyền truy cập trực tiếp vào các dịch vụ cốt lõi**.
   - Mọi quyền truy cập dữ liệu và lưu trữ đều được kiểm soát nghiêm ngặt thông qua **Capability Token** và các đường dẫn **Presigned S3 URLs** ngắn hạn do Control Plane cấp phát riêng cho từng `TRAINING_JOB_ID`.
2. **Quản lý Vòng đời Huấn luyện Toàn diện (Execution Lifecycle Management):**
   - Tự động tải mã nguồn (`SOURCE_CODE_URL`) và tập dữ liệu huấn luyện (`TRAIN_DATA_URL`) từ S3 về thư mục làm việc `/workspace`.
   - Cài đặt các thư viện phụ thuộc đặc thù của bài toán (`requirements.txt`) trong giới hạn an toàn.
   - Khởi chạy script huấn luyện chính (`ENTRY_POINT`, ví dụ: `train.py`) dưới dạng tiến trình con (subprocess), giám sát việc sử dụng tài nguyên (CPU, RAM, GPU) và hỗ trợ cơ chế ngắt/hủy tác vụ tức thời (Graceful Cancellation).
3. **Thu thập Siêu dữ liệu & Giao thức Metric Thời gian thực (Real-time Metric Protocol):**
   - Phân tích luồng đầu ra stdout/stderr để bắt các tín hiệu metric theo giao thức chuẩn: `METRIC_JSON {"epoch": 1, "loss": 0.25, "accuracy": 0.94}`.
   - Tự động đẩy các chỉ số metric và nhật ký thực thi vào Redis Stream (`training_logs:{job_id}`) hoặc Grafana Loki để người dùng có thể theo dõi tiến độ huấn luyện trực tiếp trên giao diện web.
   - Hỗ trợ MLflow Tracking để ghi nhận tham số (parameters) và siêu dữ liệu huấn luyện.
4. **Đóng gói Kết quả Huấn luyện (Output Artifact Bundling):**
   - Thu thập toàn bộ artifact mô hình đã huấn luyện trong thư mục `/workspace/model/` (hỗ trợ Scikit-Learn `.pkl`/`.joblib`, XGBoost `.xgb`, PyTorch `.pt`/`.pth`, TensorFlow/Keras `.h5`/`.keras`).
   - Tổng hợp các chỉ số giải thích mô hình (Model Insights như `feature_importance.json`, `coefficients.json`), metrics, và thông tin môi trường thành gói bundle `TrainingOutput`.
   - Nén kết quả và tải lên S3, sau đó gửi Webhook Callback báo cáo hoàn tất cho Control Plane.

```
+-----------------------------------------------------------------------------+
|                               CONTROL PLANE                                 |
|   1. Nhận yêu cầu huấn luyện từ người dùng -> Lưu TrainingJob (PENDING)     |
|   2. Sinh Capability Token & Presigned URLs cho Job                         |
|   3. Kích hoạt Worker qua Docker SDK (Local) hoặc PyTorchJob/Argo (K8s)     |
+-----------------------------------------------------------------------------+
                                       │
                                       ▼
+-----------------------------------------------------------------------------+
|                              TRAINING RUNNER                                |
|                                                                             |
|  [Giai đoạn 1: Chuẩn bị Workspace]                                          |
|  ├── Tải Source Code & Dataset từ S3 qua Presigned GET URLs                 |
|  ├── Giải nén an toàn vào /workspace/source và /workspace/input/train       |
|  └── Cài đặt dependencies: pip install -r requirements.txt                  |
|                                                                             |
|  [Giai đoạn 2: Thực thi & Giám sát]                                         |
|  ├── Chạy tiến trình con: python train.py                                   |
|  ├── Bắt đầu ra stdout -> Parse METRIC_JSON -> Stream vào Redis/Loki        |
|  └── Giám sát tài nguyên phần cứng (CPU, RAM, GPU vRAM qua NVML)            |
|                                                                             |
|  [Giai đoạn 3: Thu thập & Đóng gói Output]                                  |
|  ├── Thu thập Model Artifacts từ /workspace/model/                          |
|  ├── Trích xuất Model Insights (feature_importance, weights)                |
|  ├── Đóng gói thành TrainingOutput ZIP                                      |
|  └── Upload ZIP lên S3 qua Presigned PUT URL                                |
+-----------------------------------------------------------------------------+
                                       │
                                       │ POST /internal/webhooks/training-jobs/<id>/
                                       ▼
+-----------------------------------------------------------------------------+
|                               CONTROL PLANE                                 |
|   Cập nhật trạng thái Job -> Đăng ký ModelVersion mới vào Model Registry    |
+-----------------------------------------------------------------------------+
```

---

### 1.2. Các thành phần chính

| Module / File | Trách nhiệm chính |
|---|---|
| **`src/main.py`** | Entrypoint mỏng khởi động ứng dụng và xử lý mã lỗi thoát. |
| **`src/application.py`** | Trình điều phối toàn diện (Workflow Orchestrator): quản lý các bước tải dữ liệu, cài đặt thư viện, thực thi mã nguồn người dùng, stream logs và gửi webhook callback. |
| **`src/execution.py`** | Quản lý vòng đời tiến trình con (Subprocess Management): tạo process group mới, xử lý tín hiệu hủy tác vụ (`SIGTERM`/`SIGKILL`) để dọn sạch toàn bộ cây tiến trình, kiểm soát timeout. |
| **`src/metadata.py`** | Thu thập và xử lý các thông số siêu dữ liệu: thông số mô hình (hyperparameters), trích xuất metric kiểm thử, phân tích insight (`feature_importance.json`, `coefficients.json`), tạo file `metadata.json`. |
| **`src/resources.py`** | Đo lường mức độ tiêu thụ tài nguyên máy chủ: lấy thông số CPU, dung lượng bộ nhớ RAM sử dụng, và thông số GPU (nhiệt độ, vRAM thông qua thư viện `pynvml` nếu có card NVIDIA). |
| **`src/io.py`** | Tầng I/O an toàn: tải và đẩy file qua Presigned S3 URLs, giải nén ZIP/TAR an toàn chống traversal path. |
| **`src/config.py`** | Quản lý các biến môi trường cấu hình, đường dẫn thư mục `/workspace`, và các cờ tính năng. |
| **`src/logging_utils.py`** | Bộ quản lý log chuyên biệt: hỗ trợ stream log trực tiếp vào Redis (`training_logs:{job_id}`) và in ra stdout cho hệ thống Grafana Loki. |

---

### 1.3. Luồng hoạt động

1. **Khởi tạo và Xác thực:**
   - Training Runner khởi động, đọc các biến môi trường: `TRAINING_JOB_ID`, `CAPABILITY_TOKEN`, `SOURCE_CODE_URL`, `TRAIN_DATA_URL`, `ENTRY_POINT`.
   - Kết nối tới Redis để sẵn sàng stream log thời gian thực.
2. **Chuẩn bị Dữ liệu Huấn luyện:**
   - Tải file nén mã nguồn từ `SOURCE_CODE_URL` và giải nén vào `/workspace/source/`.
   - Tải tập dữ liệu huấn luyện từ `TRAIN_DATA_URL` và giải nén vào `/workspace/input/train/`.
   - Kiểm tra nếu tồn tại file `/workspace/source/requirements.txt`, thực thi lệnh `pip install -r requirements.txt` để nạp các thư viện phụ thuộc mà bài toán yêu cầu.
3. **Thực thi Script Huấn luyện (User Execution):**
   - Khởi chạy script người dùng chỉ định (mặc định: `train.py`) trong một tiến trình con độc lập với thư mục gốc đặt tại `/workspace/source/`.
   - Đọc luồng output stdout/stderr liên tục. Mọi dòng log thông thường sẽ được đẩy vào Redis stream.
   - Nếu dòng log bắt đầu bằng cú pháp `METRIC_JSON`, runner sẽ parse payload JSON này và lưu lại để tổng hợp thành biểu đồ tiến độ.
4. **Xử lý Hủy Tác vụ (Cancellation Handling):**
   - Nếu người dùng bấm "Cancel" trên Web Dashboard, Control Plane gửi tín hiệu `SIGTERM` tới container.
   - Module `execution.py` sẽ gửi tín hiệu ngắt tới toàn bộ nhóm tiến trình (`os.killpg`), đảm bảo không có tiến trình con chạy ngầm (zombie processes) bị bỏ sót.
5. **Tổng hợp Kết quả & Đóng gói Output:**
   - Khi tiến trình người dùng kết thúc với mã thành công `0`:
     - Quét thư mục `/workspace/model/` để thu thập file trọng số mô hình.
     - Quét các file insight nếu người dùng có ghi ra (`model_insights.json`, `feature_importance.json`).
     - Đóng gói toàn bộ model + metrics + metadata thành file ZIP `training_output.zip`.
6. **Tải lên S3 & Callback Hoàn tất:**
   - Dùng `CAPABILITY_TOKEN` gọi Control Plane xin Presigned URL để upload file `training_output.zip` lên S3.
   - Gửi Webhook callback tới `/internal/webhooks/training-jobs/<id>/` thông báo tác vụ hoàn tất thành công (`COMPLETED`) kèm tóm tắt metrics.

---

## 2. Cấu trúc cây thư mục

```text
services/training-runner/
├── Dockerfile                         # Khai báo image runtime (hỗ trợ CPU/CUDA)
├── requirements.txt                   # Thư viện phụ thuộc (mlflow, redis, pynvml, requests)
├── src/                               # Toàn bộ mã nguồn nghiệp vụ
│   ├── __init__.py
│   ├── main.py                        # Entrypoint mỏng của tiến trình
│   ├── application.py                 # Điều phối toàn bộ quy trình huấn luyện
│   ├── execution.py                   # Quản lý vòng đời subprocess và ngắt tiến trình
│   ├── metadata.py                    # Thu thập và tổng hợp thông số siêu dữ liệu
│   ├── resources.py                   # Giám sát mức sử dụng CPU, RAM và GPU
│   ├── io.py                          # Tầng truyền file Presigned S3 và giải nén an toàn
│   ├── config.py                      # Quản lý đường dẫn workspace và cấu hình môi trường
│   `-- logging_utils.py               # Quản lý stream log thời gian thực và metric logging
`-- tests/                             # Bộ kiểm thử tự động độc lập
    ├── __init__.py
    ├── conftest.py                    # Fixtures giả lập môi trường workspace và Redis
    ├── test_runner_io.py              # Kiểm thử tải/đẩy dữ liệu S3 và an toàn giải nén
    ├── test_runner_logging.py         # Kiểm thử giao thức ghi log và parse METRIC_JSON
    ├── test_runner_metadata.py        # Kiểm thử tổng hợp metadata và insights
    ├── test_runner_runtime.py         # Kiểm thử thực thi subprocess và xử lý hủy tác vụ
    `-- test_logging_utils.py          # Kiểm thử tiện ích format log
```

---

## 3. Hướng dẫn khởi chạy và các lệnh cần thiết

### 3.1. Chạy thử nghiệm qua Docker Container

Trong môi trường thực tế, container này được khởi chạy tự động bởi Control Plane hoặc Kubernetes Job. Bạn có thể chạy thử nghiệm thủ công bằng lệnh Docker:

```bash
docker run --rm \
  -e TRAINING_JOB_ID="019488a0-1000-7000-8000-000000000001" \
  -e PROJECT_ID="019488a0-1000-7000-8000-000000000002" \
  -e SOURCE_CODE_URL="https://your-s3-presigned-url/source.zip" \
  -e TRAIN_DATA_URL="https://your-s3-presigned-url/data.csv" \
  -e ENTRY_POINT="train.py" \
  -e CAPABILITY_TOKEN="your-short-lived-capability-token" \
  -e CONTROL_PLANE_WEBHOOK_URL="http://control-plane:8000/internal/webhooks/training-jobs/019488a0-1000-7000-8000-000000000001/" \
  -e REDIS_URL="redis://redis:6379/1" \
  mlops-paas-training-runner:latest
```

### 3.2. Chạy thử nghiệm trực tiếp trên máy chủ / Virtualenv

#### Bước 1: Chuẩn bị môi trường ảo
```bash
cd services/training-runner
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
export TRAINING_JOB_ID=test-job-uuid
export ENTRY_POINT=train.py

# Chạy trực tiếp qua entrypoint chuẩn
python -m src.main
```

---

### 3.3. Các biến môi trường quan trọng

| Tên biến | Bắt buộc | Mô tả chức năng |
|---|---|---|
| `TRAINING_JOB_ID` | Có | UUID định danh duy nhất của phiên huấn luyện. |
| `PROJECT_ID` | Có | UUID của dự án sở hữu bài toán huấn luyện. |
| `ENTRY_POINT` | Có | Tên file script thực thi chính (mặc định: `train.py`). |
| `SOURCE_CODE_URL` | Có | Presigned GET URL tải mã nguồn huấn luyện. |
| `TRAIN_DATA_URL` | Có | Presigned GET URL tải dữ liệu huấn luyện đầu vào. |
| `CAPABILITY_TOKEN` | Có | Token ký số ngắn hạn dùng để yêu cầu Presigned PUT URL tải kết quả lên S3. |
| `CONTROL_PLANE_WEBHOOK_URL` | Có | URL nhận webhook callback báo cáo tiến độ và kết quả. |
| `REDIS_URL` | Không | Địa chỉ Redis để stream trực tiếp logs (`training_logs:{job_id}`). |
| `LOG_STORAGE_BACKEND` | Không | Cấu hình backend lưu logs: `redis` (mặc định) hoặc `loki`. |

---

### 3.4. Kiểm tra chất lượng & Chạy Unit Test (Quality Gates)

```bash
# 1. Kiểm tra quy chuẩn code với Ruff
python -m ruff check .

# 2. Chạy toàn bộ bộ kiểm thử tự động với Pytest
python -m pytest --cov=src --cov-report=term-missing
```

---

## 4. Các chú ý quan trọng (Architectural Constraints & Caveats)

> [!IMPORTANT]
> **Định Danh Bất Biến (Identifier Invariant):**
> Toàn bộ logic nhận diện của Training Runner bắt buộc sử dụng định danh duy nhất `TRAINING_JOB_ID`. **Tuyệt đối không sử dụng định danh cũ không tường minh như `MODEL_ID`**.

> [!CAUTION]
> **Cô Lập Tuyệt Đối (Untrusted Code Isolation):**
> Mã nguồn huấn luyện của người dùng có thể chứa các đoạn mã độc hại hoặc thư viện không an toàn. Do đó:
> - Container Training Runner không bao giờ được gán IAM Role có quyền thao tác trực tiếp trên AWS ngoài các Presigned URLs được cấp phát.
> - Không chia sẻ quyền truy cập cơ sở dữ liệu PostgreSQL hoặc quyền ghi cấu hình Redis hệ thống cho container này.

> [!WARNING]
> **Cơ Chế Hủy Tác Vụ An Toàn (Process Tree Cleanup):**
> Script của người dùng có thể spawn nhiều tiến trình con hoặc worker threads (ví dụ: PyTorch DataLoader với nhiều `num_workers`). Khi nhận tín hiệu ngắt (`SIGTERM`), Training Runner sử dụng nhóm tiến trình (`process group`) để đảm bảo ngắt sạch sẽ toàn bộ cây tiến trình, tránh gây rò rỉ bộ nhớ hoặc chiếm dụng GPU vRAM.

> [!TIP]
> **Chuẩn Định Dạng Metric Thời Gian Thực:**
> Để biểu đồ tiến độ trên giao diện người dùng hiển thị đúng, mã nguồn người dùng chỉ cần in ra stdout theo cú pháp:
> `print("METRIC_JSON " + json.dumps({"epoch": 1, "loss": 0.35, "val_accuracy": 0.91}))`
> Hệ thống sẽ tự động bắt dòng log này và chuyển thành dữ liệu chuỗi thời gian (Time-series Metric) mà không yêu cầu cài đặt thêm SDK phức tạp.
