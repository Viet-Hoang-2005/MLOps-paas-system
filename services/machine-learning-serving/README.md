# Machine Learning Serving — Worker Phục Vụ Suy Luận Mô Hình Học Máy Cổ Điển

Thư mục `services/machine-learning-serving/` chứa mã nguồn của **Machine Learning Serving Service**, một Worker Engine phi trạng thái (Stateless Worker) phát triển trên nền tảng FastAPI. Dịch vụ chuyên trách phục vụ dự đoán thời gian thực cho các mô hình học máy truyền thống và dữ liệu dạng bảng (Tabular / Classical ML như Scikit-Learn, XGBoost, LightGBM, CatBoost) được đóng gói theo chuẩn MLflow Artifacts.

---

## 1. Giới thiệu

### 1.1. Vai trò trong hệ thống

Trong kiến trúc tổng thể của MLOps PaaS, `machine-learning-serving` hoạt động ở tầng thực thi suy luận (Inference Execution Layer) nằm sau Gateway `model-server`:

1. **Phục vụ Suy luận Học máy Dạng bảng Tối ưu (Optimized Tabular ML Inference):**
   - Chuyên biệt hóa để thực thi các pipeline Scikit-Learn, mô hình cây quyết định (Random Forest, Gradient Boosting), và các thuật toán phân lớp/hồi quy phổ biến.
   - Không bị quá tải bởi các thư viện Deep Learning cồng kềnh (PyTorch/TensorFlow), giúp giảm đáng kể dung lượng container image và thời gian khởi động (Cold Start Time).
2. **Tương thích Tiêu chuẩn MLflow Model Flavor:**
   - Tự động nhận diện và nạp các mô hình được đóng gói dưới định dạng MLflow Model (`MLmodel`), hỗ trợ cả flavor `mlflow.sklearn` và `mlflow.pyfunc`.
   - Đọc trực tiếp chữ ký mô hình (MLflow Model Signature) để xác định danh sách các cột đặc trưng (Features) và kiểu dữ liệu mà mô hình mong đợi.
3. **Cơ chế Cache Bộ nhớ & Chuẩn hóa Dữ liệu Tự động:**
   - Lưu trữ mô hình đã nạp trong bộ nhớ RAM (`MODEL_CACHE`) theo định danh phiên bản, giúp phục vụ các request tiếp theo với độ trễ tối thiểu (sub-millisecond latency).
   - Tự động sắp xếp lại thứ tự các cột đặc trưng (Feature Column Ordering) từ dictionary JSON đầu vào để đảm bảo đúng với thứ tự mảng NumPy / Pandas DataFrame lúc huấn luyện.
   - Trích xuất xác suất dự đoán (`predict_proba`) để tính toán điểm tin cậy (**Confidence Score**) khi mô hình hỗ trợ.
4. **Kiến trúc Phi trạng thái (Stateless Worker):**
   - Dịch vụ không lưu trữ session, không kết nối trực tiếp đến cơ sở dữ liệu quan hệ, và không tự xác thực người dùng (trách nhiệm này được ủy quyền hoàn toàn cho `model-server`).

```
+-------------------------------------------------------------+
|                Model Server (Inference Gateway)             |
|   - Xác thực JWT / API Key                                  |
|   - Kiểm tra quyền truy cập mô hình                         |
+-------------------------------------------------------------+
                              │
                              │ POST /predict (Payload JSON)
                              ▼
+-------------------------------------------------------------+
|             MACHINE LEARNING SERVING WORKER                 |
|                                                             |
|  +-------------------------------------------------------+  |
|  |                 FastAPI Application                   |  |
|  |  - Endpoint /health (Trạng thái nạp mô hình)          |  |
|  |  - Endpoint /predict (Thực thi suy luận)              |  |
|  +-------------------------------------------------------+  |
|                             │                               |
|                             ▼                               |
|  +-------------------------------------------------------+  |
|  |               Model Loading & Caching                 |  |
|  |  - Tải artifact từ S3 / Local (MLmodel format)        |  |
|  |  - Trích xuất Expected Features & Class Labels        |  |
|  |  - Cache instance mô hình trong bộ nhớ                |  |
|  +-------------------------------------------------------+  |
|                             │                               |
|                             ▼                               |
|  +-------------------------------------------------------+  |
|  |                  Inference Engine                     |  |
|  |  - Kiểm tra và sắp xếp thứ tự cột đặc trưng           |  |
|  |  - Chạy predict() & predict_proba()                   |  |
|  |  - Chuẩn hóa kết quả dự đoán và điểm tin cậy          |  |
|  +-------------------------------------------------------+  |
+-------------------------------------------------------------+
```

---

### 1.2. Các thành phần chính

| Module / File | Trách nhiệm chính |
|---|---|
| **`src/main.py`** | Entrypoint mỏng xuất bản đối tượng ASGI `app` từ `src.api:app`. |
| **`src/api.py`** | Ứng dụng FastAPI khai báo vòng đời (`lifespan`), middleware ghi nhật ký request và các endpoints: `GET /`, `GET /health`, `POST /predict`. |
| **`src/loading.py`** | Tầng nạp mô hình: tải artifact từ S3 (`MODEL_URI`) hoặc ổ đĩa, phân tích file `MLmodel`, quản lý từ điển cache `MODEL_CACHE`, phân tích nhãn phân lớp (Label mapping). |
| **`src/inference.py`** | Tầng thực thi dự đoán: chuyển đổi JSON features sang DataFrame, kiểm tra đối chiếu signature, gọi hàm `predict()`/`predict_proba()` và chuẩn hóa kết quả đầu ra. |
| **`src/schemas.py`** | Định nghĩa cấu trúc dữ liệu đầu vào `InferenceRequest` bằng Pydantic. |
| **`src/logging_utils.py`** | Middleware đo lường hiệu năng và chuẩn hóa cấu trúc nhật ký log (Console / JSON một dòng). |
| **`src/uvicorn_entrypoint.py`** | Script hỗ trợ khởi động Uvicorn server với các tham số cấu hình. |

---

### 1.3. Luồng hoạt động

1. **Khởi động và Sẵn sàng (Startup & Health Check):**
   - Khi container khởi động, dịch vụ đọc biến môi trường `MODEL_VERSION_ID` và `MODEL_URI`.
   - Endpoint `GET /health` kiểm tra xem mô hình đã được tải thành công vào bộ nhớ hay chưa và trả về thông tin định danh: `tenant_id`, `project_id`, `model_version_id`, `model_loaded`.
2. **Tiếp nhận Yêu cầu Dự đoán (`POST /predict`):**
   - Worker tiếp nhận payload từ `model-server` gồm:
     ```json
     {
       "features": {
         "feature_a": 12.5,
         "feature_b": 0.85
       },
       "model_version_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
     }
     ```
3. **Kiểm tra và Nạp Mô hình từ Bộ đệm:**
   - Tra cứu `MODEL_CACHE` theo `model_version_id`. Nếu chưa có trong cache, hàm `load_model_from_uri` sẽ tải artifact, nạp mô hình và lưu lại vào cache.
4. **Đối chiếu và Sắp xếp Cột Đặc trưng:**
   - So sánh danh sách features trong request với danh sách `expected_features` trích xuất từ chữ ký MLflow.
   - Nếu thiếu bất kỳ đặc trưng bắt buộc nào, worker lập tức trả về lỗi `HTTP 400 Bad Request` kèm thông báo chi tiết.
   - Tự động sắp xếp lại các cột theo đúng trật tự ma trận lúc huấn luyện.
5. **Thực thi Suy luận & Tính Điểm Tin cậy:**
   - Gọi phương thức `model.predict(input_data)`.
   - Nếu mô hình hỗ trợ `predict_proba`, tính toán xác suất cao nhất làm điểm tin cậy `confidence` (giá trị từ `0.0` đến `1.0`).
6. **Phản hồi Chuẩn hóa:**
   - Trả về kết quả JSON chuẩn hóa:
     ```json
     {
       "success": true,
       "prediction": "benign",
       "confidence": 0.985,
       "model_version_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
       "engine": "machine-learning-serving"
     }
     ```

---

## 2. Cấu trúc cây thư mục

```text
services/machine-learning-serving/
├── Dockerfile                         # Khai báo container runtime tối ưu cho Sklearn/XGBoost
├── requirements.txt                   # Danh sách thư viện Python phụ thuộc
├── README.md                          # Tài liệu kỹ thuật của service
├── src/                               # Toàn bộ mã nguồn nghiệp vụ
│   ├── __init__.py
│   ├── main.py                        # Entrypoint mỏng cho ASGI server
│   ├── api.py                         # FastAPI App, routes và health endpoints
│   ├── inference.py                   # Logic validate features, chạy predict và confidence
│   ├── loading.py                     # Quản lý tải artifact, phân tích MLmodel và in-memory cache
│   ├── schemas.py                     # Định nghĩa Pydantic schema cho request payload
│   ├── uvicorn_entrypoint.py          # Script khởi chạy tiến trình Uvicorn
│   `-- logging_utils.py               # Middleware logging ngữ cảnh và summary metrics
`-- tests/                             # Bộ kiểm thử đơn vị
    ├── __init__.py
    ├── asgi_smoke.py                  # Smoke test cho ASGI server
    ├── test_api.py                    # Kiểm thử các endpoint /health và /predict
    ├── test_inference.py              # Kiểm thử xử lý lỗi dữ liệu đầu vào và tính toán kết quả
    ├── test_loading.py                # Kiểm thử cơ chế nạp artifact và quản lý cache
    ├── test_logging.py                # Kiểm thử định dạng logger
    `-- test_logging_utils.py          # Kiểm thử middleware ghi vết
```

---

## 3. Hướng dẫn khởi chạy và các lệnh cần thiết

### 3.1. Khởi chạy bằng Docker Compose (Môi trường phát triển cục bộ)

Mặc định service được cấu hình lắng nghe trên cổng `5001`:

```bash
# Khởi động dịch vụ ML Serving
docker compose up -d machine-learning-serving

# Theo dõi nhật ký thực thi
docker compose logs -f machine-learning-serving
```

Kiểm tra trạng thái sức khỏe:
```bash
curl http://localhost:5001/health
```

### 3.2. Khởi chạy trực tiếp trên máy chủ / Virtualenv (Không dùng Docker)

#### Bước 1: Chuẩn bị môi trường ảo
```bash
# Chuyển vào thư mục service
cd services/machine-learning-serving

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
export MODEL_VERSION_ID=your-model-version-uuid
export MODEL_URI=s3://mlops-paas-artifacts/models/your-model/
export PROJECT_ID=your-project-uuid
export TENANT_ID=your-tenant-uuid
```

#### Bước 3: Khởi chạy Server Uvicorn
```bash
uvicorn src.main:app --host 0.0.0.0 --port 5001 --reload
```

---

### 3.3. Các biến môi trường quan trọng

| Tên biến | Bắt buộc | Mô tả chức năng |
|---|---|---|
| `MODEL_VERSION_ID` | Có | UUID xác định phiên bản mô hình được nạp. |
| `MODEL_URI` | Có | Đường dẫn S3 hoặc đường dẫn thư mục cục bộ chứa MLflow artifact. |
| `PROJECT_ID` | Có | UUID xác định dự án sở hữu mô hình. |
| `TENANT_ID` | Không | UUID xác định người dùng/tenant sở hữu. |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Tùy chọn | Thông tin xác thực AWS để tải artifact từ S3 (khi chạy local). |
| `AWS_DEFAULT_REGION` | Không | Vùng AWS S3 (mặc định: `ap-southeast-1`). |

---

### 3.4. Kiểm tra chất lượng & Chạy Unit Test (Quality Gates)

```bash
# 1. Kiểm tra Linting với Ruff
python -m ruff check .

# 2. Chạy toàn bộ unit test với Pytest và đo độ bao phủ
python -m pytest --cov=src --cov-report=term-missing
```

---

## 4. Các chú ý quan trọng (Architectural Constraints & Caveats)

> [!IMPORTANT]
> **Bất Biến Nhận Diện Runtime (Identifier Invariant):**
> Định danh mô hình bắt buộc phải sử dụng cặp `PROJECT_ID` và `MODEL_VERSION_ID`. **Tuyệt đối không được bổ sung fallback cho định danh cũ `MODEL_ID`**.

> [!WARNING]
> **Không Tải Dữ Liệu Ngoại Vi Khi Import (No Network I/O at Import Time):**
> Mã nguồn trong các module tuyệt đối không được thực hiện kết nối S3 hoặc tải model ngay khi import file. Toàn bộ logic tải model phải được kích hoạt bên trong hàm khởi tạo hoặc khi xử lý request để đảm bảo an toàn cho quá trình kiểm thử đơn vị (Unit Testing) và khởi động tiến trình.

> [!CAUTION]
> **Quy Chuẩn Phân Loại Lỗi HTTP:**
> - Thiếu đặc trưng (Missing Features), sai lệch tên cột hoặc sai định dạng dữ liệu đầu vào **bắt buộc phải trả về mã `HTTP 400 Bad Request`** (Client Error).
> - Chỉ trả về mã `HTTP 500 Internal Server Error` khi xảy ra sự cố sập runtime bất khả kháng trong quá trình tính toán của thuật toán.

> [!TIP]
> **Khả Năng Xử Lý Đồng Thời:**
> Do các pipeline Scikit-Learn giải phóng GIL trong các tác vụ tính toán nặng với thư viện C-extensions (NumPy / OpenMP), dịch vụ có thể xử lý đa luồng tốt trên Uvicorn với nhiều worker threads mà không bị nghẽn CPU.
