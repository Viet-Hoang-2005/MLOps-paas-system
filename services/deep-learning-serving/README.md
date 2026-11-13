# Deep Learning Serving — Worker Phục Vụ Suy Luận Mô Hình Học Sâu (Deep Learning)

Thư mục `services/deep-learning-serving/` chứa mã nguồn của **Deep Learning Serving Service**, một Worker Engine chuyên biệt phát triển trên nền tảng **BentoML** kết hợp cùng **MLflow PyFunc**. Dịch vụ được thiết kế để phục vụ suy luận thời gian thực cho các mô hình Học sâu phức tạp (Deep Learning: PyTorch, TensorFlow, Keras, HuggingFace Transformers) với khả năng tối ưu hóa tính toán trên CPU/GPU và xử lý dữ liệu tensor linh hoạt.

---

## 1. Giới thiệu

### 1.1. Vai trò trong hệ thống

Trong kiến trúc MLOps PaaS, `deep-learning-serving` chịu trách nhiệm xử lý các tác vụ suy luận có khối lượng tính toán lớn (Compute-Intensive Inference) do `model-server` điều hướng tới:

1. **Phục vụ Suy luận Học sâu Hiệu năng cao (High-Performance DL Inference):**
   - Tận dụng sức mạnh của BentoML Service Framework để quản lý vòng đời phục vụ, tối ưu luồng dữ liệu (I/O pipeline), hỗ trợ điều tiết lưu lượng (Traffic Management), và tự động gom cụm vi mô nếu cần mở rộng (Adaptive Batching).
2. **Khả năng tương thích Toàn diện qua MLflow PyFunc:**
   - Sử dụng chuẩn đóng gói `mlflow.pyfunc` để nạp mọi mô hình Deep Learning bất kể framework gốc (PyTorch `.pt`/`.pth`, TensorFlow SavedModel, ONNX, Keras `.h5`/`.keras`).
   - Tự động nhận diện cấu trúc thư mục artifact (thư mục gốc hoặc thư mục con chứa `MLmodel`).
3. **Bộ chuyển đổi Định dạng Tensor Đa năng (Universal Input/Output Normalization):**
   - Chấp nhận linh hoạt các cấu trúc dữ liệu đầu vào từ client: JSON dictionary đơn lẻ (scalar dict), dictionary theo cột (column-oriented dict), danh sách đa chiều (nested lists) hoặc mảng số.
   - Tự động chuyển đổi sang Pandas DataFrame / NumPy Array để đưa vào mô hình Deep Learning, đồng thời chuẩn hóa các tensor đầu ra (PyTorch Tensor, TF Tensor, mảng NumPy) thành dữ liệu số / danh sách JSON thuần túy để trả về cho client.
4. **Cơ chế Tự phục hồi và Khởi động An toàn (Fault-Tolerant Startup):**
   - Logic nạp mô hình khi khởi động (`load_runtime_model`) được bao bọc an toàn. Nếu việc tải mô hình từ S3 thất bại, service sẽ gán `self.model = None` và phản ánh trạng thái qua endpoint `/health` thay vì để container sập (crash loop) ngay lập tức.

```
+-------------------------------------------------------------+
|                Model Server (Inference Gateway)             |
|   - Xác thực JWT / API Key                                  |
|   - Kiểm tra quyền truy cập mô hình                         |
+-------------------------------------------------------------+
                              │
                              │ POST /predict (HTTP/JSON)
                              ▼
+-------------------------------------------------------------+
|               DEEP LEARNING SERVING WORKER                  |
|                 (BentoML Service Engine)                    |
|                                                             |
|  +-------------------------------------------------------+  |
|  |                 BentoML Service App                   |  |
|  |  - Endpoint /health (Trạng thái nạp mô hình)          |  |
|  |  - Endpoint /predict (Thực thi suy luận)              |  |
|  +-------------------------------------------------------+  |
|                             │                               |
|                             ▼                               |
|  +-------------------------------------------------------+  |
|  |          MLflow PyFunc Artifact Loader                |  |
|  |  - Tải artifact từ S3 / Local Storage                 |  |
|  |  - Nạp PyTorch / TensorFlow / Keras Engine            |  |
|  |  - Quản lý tài nguyên CPU / GPU Workers               |  |
|  +-------------------------------------------------------+  |
|                             │                               |
|                             ▼                               |
|  +-------------------------------------------------------+  |
|  |           Input/Output Tensor Normalization           |  |
|  |  - Chuyển đổi JSON Dict / Lists -> Input Form         |  |
|  |  - Thực thi tính toán mô hình                         |  |
|  |  - Chuyển đổi Tensor Outputs -> JSON Response         |  |
|  +-------------------------------------------------------+  |
+-------------------------------------------------------------+
```

---

### 1.2. Các thành phần chính

| Module / File | Trách nhiệm chính |
|---|---|
| **`src/main.py`** | Entrypoint chuẩn xuất bản lớp dịch vụ `DeepLearningModelService`. |
| **`src/service.py`** | BentoML Service class (`@bentoml.service`): quản lý cấu hình tài nguyên (`cpu: 2`, `timeout: 60`), khởi tạo model trong `__init__`, định nghĩa các endpoint `@bentoml.api` cho `/predict` và `/health`, tích hợp middleware ghi log. |
| **`src/loading.py`** | Tầng nạp mô hình: tải artifact từ S3 (`MODEL_URI`), giải nén và phân tích cấu trúc cây thư mục để tìm đúng thư mục MLflow, nạp mô hình qua `mlflow.pyfunc.load_model`. |
| **`src/inference.py`** | Tầng suy luận: phân tích cấu trúc dữ liệu đầu vào, ép kiểu sang DataFrame chuẩn, gọi hàm `model.predict()` và chuẩn hóa các kiểu dữ liệu tensor đặc thù thành JSON an toàn. |
| **`src/logging_utils.py`** | Tiện ích chuẩn hóa logging (Console / JSON một dòng) và bộ đệm ngữ cảnh phân tán (`RequestLoggingMiddleware`). |

---

### 1.3. Luồng hoạt động

1. **Khởi tạo Dịch vụ BentoML (Service Lifecycle):**
   - BentoML khởi tạo instance của `DeepLearningModelService`.
   - Trích xuất `MODEL_VERSION_ID` và `MODEL_URI` từ biến môi trường.
   - Gọi hàm `load_runtime_model`:
     - Nếu có `MODEL_URI`, tải artifact từ S3 về thư mục tạm, xác định file `MLmodel` và nạp vào bộ nhớ.
     - Nếu không có `MODEL_URI`, kiểm tra thư mục artifact mặc định `/app/model_artifact`.
   - Nếu nạp thành công, biến `self.model` sẵn sàng. Nếu xảy ra lỗi ngoại lệ, ghi log cảnh báo và giữ `self.model = None`.
2. **Kiểm tra Sức khỏe (`GET /health`):**
   - Trả về thông tin trạng thái hoạt động:
     ```json
     {
       "status": "healthy",
       "model_loaded": true,
       "runtime": "deep-learning-serving-bentoml",
       "project_id": "019488a0-2f22-777e-967a-e49d63c5a6c0",
       "model_version_id": "019488a0-3882-7aa1-a3f2-123456789abc",
       "engine": "deep-learning-serving"
     }
     ```
3. **Tiếp nhận Yêu cầu Suy luận (`POST /predict`):**
   - Nếu `self.model is None`, lập tức trả về lỗi runtime rõ ràng (`RuntimeError: Model failed to load at startup`).
   - Hàm `run_inference(self.model, payload)` tiếp nhận dữ liệu đầu vào.
4. **Chuẩn hóa Dữ liệu Đầu vào (Input Transformation):**
   - Nhận diện kiểu dữ liệu đầu vào:
     - Dictionary vô hướng: `{"x1": 1.0, "x2": 2.0}` $\rightarrow$ Chuyển thành DataFrame 1 dòng.
     - Dictionary dạng cột: `{"x1": [1.0, 3.0], "x2": [2.0, 4.0]}` $\rightarrow$ Chuyển thành DataFrame đa dòng.
     - Danh sách hoặc mảng m-chiều $\rightarrow$ Chuyển thành cấu trúc tương thích với `pyfunc.predict()`.
5. **Thực thi Suy luận & Chuẩn hóa Đầu ra:**
   - Thực thi `self.model.predict(input_data)`.
   - Chuyển đổi kết quả (mảng NumPy 1D/2D, PyTorch Tensor) thành kiểu dữ liệu nguyên thủy (float, int, list).
6. **Phản hồi Chuẩn hóa:**
   - Trả về payload kết quả cho Model Server:
     ```json
     {
       "success": true,
       "prediction": [0.942, 0.058],
       "confidence": null,
       "project_id": "019488a0-2f22-777e-967a-e49d63c5a6c0",
       "model_version_id": "019488a0-3882-7aa1-a3f2-123456789abc",
       "engine": "deep-learning-serving"
     }
     ```

---

## 2. Cấu trúc cây thư mục

```text
services/deep-learning-serving/
├── Dockerfile                         # Khai báo image runtime hỗ trợ BentoML & PyTorch/TensorFlow
├── requirements.txt                   # Danh sách thư viện Python phụ thuộc (BentoML, MLflow, Torch/TF)
├── README.md                          # Tài liệu kỹ thuật của service
├── src/                               # Toàn bộ mã nguồn nghiệp vụ
│   ├── __init__.py
│   ├── main.py                        # Entrypoint xuất bản BentoML Service class
│   ├── service.py                     # BentoML Service class, khai báo API routes và lifecycle
│   ├── loading.py                     # Tầng tải artifact và nạp MLflow PyFunc model
│   ├── inference.py                   # Chuyển đổi tensor đa năng và chuẩn hóa output
│   `-- logging_utils.py               # Middleware và bộ lọc log cho BentoML
`-- tests/                             # Bộ kiểm thử tự động
    ├── __init__.py
    ├── test_loading.py                # Kiểm thử nạp artifact và xử lý đường dẫn lồng nhau
    ├── test_service.py                # Kiểm thử các endpoint BentoML /health và /predict
    ├── test_logging.py                # Kiểm thử cấu hình logger
    `-- test_logging_utils.py          # Kiểm thử middleware ghi log
```

---

## 3. Hướng dẫn khởi chạy và các lệnh cần thiết

### 3.1. Khởi chạy bằng Docker Compose (Môi trường phát triển cục bộ)

Service được cấu hình để phục vụ qua BentoML runtime:

```bash
# Khởi động dịch vụ Deep Learning Serving
docker compose up -d deep-learning-serving

# Theo dõi nhật ký thực thi
docker compose logs -f deep-learning-serving
```

Kiểm tra trạng thái sức khỏe:
```bash
curl http://localhost:5004/health
```

### 3.2. Khởi chạy trực tiếp trên máy chủ / Virtualenv (Không dùng Docker)

#### Bước 1: Chuẩn bị môi trường ảo
```bash
# Chuyển vào thư mục service
cd services/deep-learning-serving

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
export MODEL_URI=s3://mlops-paas-artifacts/models/your-deep-model/
export PROJECT_ID=your-project-uuid
```

#### Bước 3: Khởi chạy BentoML Server
```bash
bentoml serve src.main:DeepLearningModelService --port 5004 --reload
```

---

### 3.3. Các biến môi trường quan trọng

| Tên biến | Bắt buộc | Mô tả chức năng |
|---|---|---|
| `MODEL_VERSION_ID` | Có | UUID xác định phiên bản mô hình Học sâu được nạp. |
| `MODEL_URI` | Có | Đường dẫn S3 hoặc đường dẫn đĩa cục bộ chứa artifact. |
| `PROJECT_ID` | Có | UUID xác định dự án sở hữu mô hình. |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Tùy chọn | Thông tin xác thực AWS để tải artifact từ S3. |
| `AWS_DEFAULT_REGION` | Không | Vùng AWS S3 (mặc định: `ap-southeast-1`). |

---

### 3.4. Kiểm tra chất lượng & Chạy Unit Test (Quality Gates)

```bash
# 1. Kiểm tra Linting với Ruff
python -m ruff check .

# 2. Chạy toàn bộ bộ kiểm thử tự động với Pytest và đo độ bao phủ
python -m pytest --cov=src --cov-report=term-missing
```

---

## 4. Các chú ý quan trọng (Architectural Constraints & Caveats)

> [!IMPORTANT]
> **Định Danh Bất Biến (Identifier Invariant):**
> Tương tự như `machine-learning-serving`, service bắt buộc phải sử dụng cặp `PROJECT_ID` và `MODEL_VERSION_ID`. **Tuyệt đối không bổ sung fallback cho định danh cũ `MODEL_ID`**.

> [!WARNING]
> **Nạp Mô Hình An Toàn Trong Quá Trình Khởi Động (Monkeypatchable Loading):**
> Hàm `load_runtime_model` được tách biệt hoàn toàn để hỗ trợ việc monkeypatch trong các bài kiểm thử đơn vị. Nếu quá trình tải mô hình thất bại, biến `self.model` phải được gán về `None` để phản ánh trung thực qua endpoint `/health`, không được để sập tiến trình đột ngột.

> [!TIP]
> **Quản Trị Tài Nguyên Tính Toán (Resource Allocation):**
> Cấu hình `@bentoml.service(resources={"cpu": "2"}, traffic={"timeout": 60})` giới hạn số lượng tài nguyên mặc định. Trên môi trường Kubernetes sản xuất có gắn GPU, cấu hình tài nguyên sẽ được điều chỉnh tự động qua Kubernetes deployment limits (`nvidia.com/gpu: 1`) để tăng tốc xử lý ma trận.
