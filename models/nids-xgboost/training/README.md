# NIDS XGBoost training

Trainer cho CSV CICIDS2017 đã xử lý: **52 numeric features + cột Label**.
Không nhận trực tiếp CSV flow thô, không chạy preprocessing notebook, không tái
lập thực nghiệm drift của paper và không tự lấy dữ liệu từ Internet/S3.

## Chạy trên nền tảng

Tạo Training Job, đưa các file dưới đây vào Input, chọn `train.py` làm entry
point và chọn Framework **XGBoost**:

```text
Input/
├── train.py
├── requirements.txt
├── config.json
├── feature_schema.json
└── data/
    └── train.csv
```

Copy một CSV thích hợp từ `models/nids-xgboost/data/` vào `data/train.csv`, hoặc
sửa `train_csv` trong config để trỏ đúng vị trí upload (kể cả thư mục con).
Không upload đồng thời mọi dataset nếu chỉ dùng một file. `requirements.txt`
phải nằm ở gốc Input; runner tự cài dependencies. Không cần nhập URI/token MLflow
hoặc credentials trong Environment/Secrets: platform cấp tracking capability.

Chọn CPU/RAM, GPU tùy nhu cầu và runtime tối đa trong UI rồi Run. Script không
thay đổi quota/runtime được chọn, tự giảm mẫu hoặc chuyển sang Random Forest.
Log progress xuất mỗi 10 boosting rounds; learning curves gửi từng round.

## Cấu hình

| Trường | Mặc định / ý nghĩa |
|---|---|
| `train_csv`, `feature_schema` | `data/train.csv`, `feature_schema.json`; phải là file bên trong Input |
| `classification_mode` | `binary`: BENIGN/Normal (không phân biệt hoa thường) → 0, các nhãn khác → ATTACK/1; `multiclass`: giữ nhãn đã trim và sắp xếp mapping xác định |
| `label_column` | `Label`; không tự suy đoán cột cuối |
| `seed` | `42` |
| `validation_fraction`, `test_fraction` | `0.15`, `0.15`; phần còn lại train, làm tròn số mẫu lên cho validation/test |
| `device` | `auto`, hoặc ép `cpu` / `cuda` |
| `max_threads` | `null`: tính theo CPU affinity/quota cgroup; số nguyên dương chỉ giảm giới hạn này |
| `n_estimators`, `early_stopping_rounds` | Tối đa `500` vòng, dừng sau `30` vòng validation không cải thiện |
| `max_depth`, `learning_rate` | `6`, `0.1` |
| `subsample`, `colsample_bytree` | `0.8`, `0.8` |

Tên/thứ tự 52 feature được lưu trong schema; CSV có thể đổi thứ tự cột nhưng
script luôn sắp theo schema. Không cho thiếu/thừa feature, tên cột trùng hoặc
label trùng tên feature. Hàng thiếu nhãn, không numeric, vô hạn hoặc vượt miền
float32 bị loại và thống kê; không tự điền 0 hay encode cột feature dạng text.

Loại duplicate feature trước khi split; vector giống nhau nhưng nhãn target
khác nhau bị từ chối. Trong binary mode, các họ attack đã được gộp thành ATTACK
trước bước này. Mỗi split phải có đủ mọi lớp, thiếu mẫu thì báo lỗi thay vì bỏ
stratification. Trọng số cân bằng lớp chỉ được tính từ train. Validation phục vụ
early stopping; test chỉ phục vụ đánh giá cuối. Đây là **random holdout** trên
dữ liệu đã xử lý, không chứng minh tính độc lập theo host/session/time, không
loại được leakage đã xảy ra trong preprocessing upstream.

## CPU và GPU

`auto` dùng CUDA nếu `nvidia-smi` xác nhận đúng một GPU nhìn thấy trong container,
ngược lại dùng CPU khi không có công cụ/thiết bị. Probe lỗi, nhiều GPU hoặc CUDA
lỗi không âm thầm fallback CPU. `cuda` bắt buộc có GPU. Callback còn kiểm tra
thiết bị thực tế để bắt trường hợp XGBoost tự fallback. Không truyền UUID/card
index của host vào config; Docker/Kubernetes đã giới hạn GPU được cấp.

Dependency CUDA/driver phải phù hợp với wheel XGBoost 2.0.3. Kiểm tra được GPU
không bảo đảm model/batch/dataset vừa VRAM. Khi chạy CPU nên chọn No GPU để không
giữ GPU không dùng. Dataset lớn vẫn có thể hết RAM; script đọc CSV vào bộ nhớ.

## Tracking và output

- MLflow chỉ dùng `create_run` và `log_batch` đã có ở Control Plane. Endpoint
  `create_run` gắn vào job của capability hiện tại, không tạo Training Job mới.
  Không tạo experiment, autolog, registry hoặc upload model qua MLflow từ script.
- Chuỗi `train_logloss`/`validation_logloss` (hoặc `mlogloss`) có step bắt đầu 0;
  khác tên metrics cuối (`accuracy`, `f1_macro`, v.v.). Không phát `METRIC_JSON`.
- URI runtime có hậu tố `/api/2.0/mlflow` được bỏ hậu tố khi truyền cho SDK,
  vì SDK tự thêm prefix đó. Không sửa URI của platform hoặc ghi token ra log.
- Lỗi tracking đầu tiên có cảnh báo đã che chi tiết, tắt các lần gửi còn lại;
  JSON/model vẫn được xuất. Runner có luồng thu thập/upload riêng sau process.

```text
SM_MODEL_DIR/
├── model.joblib          # XGBClassifier CPU, chỉ giữ cây đến best iteration
├── label_mapping.json   # ví dụ {"0": "BENIGN", "1": "ATTACK"}
├── input_schema.json    # JSON Schema: 52 trường number, x-feature-order giữ thứ tự
└── training_report.json # confusion matrix, per-class, curves, cleaning/split

SM_OUTPUT_DIR/
├── metrics.json
├── params.json
├── model_insights.json
└── feature_importance.json
```

Xuất `model.joblib` thay vì Booster `.xgb` vì serving hiện tại cần `predict()`
trả **nhãn**, không phải xác suất. Đây vẫn là model XGBoost, chọn flavor
**XGBoost** khi Build. Model không pickle callback, tracking client hoặc code
của script. Trainer kiểm tra dự đoán và xác suất sau load lại; artifact chỉ
được công bố bởi runner sau process thành công và upload xác minh.

Chất lượng test: accuracy, precision/recall/F1 macro/weighted, ROC-AUC khi tính
được; binary còn có attack recall/benign FPR. Chỉ số không xác định được ghi
`null` và lý do trong report, không giả thành 0. Mean macro/weighted theo quy tắc
scikit-learn bỏ các thành phần không xác định; per-class report nêu rõ lớp nào
bị thiếu giá trị. Feature importance là **gain**, không phải diễn giải nhân quả.

`training_report.json` được giữ trong model archive vì runner hiện chỉ thu nhận
phần insight chuẩn hóa, không giữ toàn bộ trường bổ sung của model_insights.
Input schema và mapping là metadata; không tự cập nhật Model Preview/Project.
Không tự thu thập Work làm artifact. Save/gán Project và Build vẫn theo UI.

## Chạy và kiểm thử ngoài nền tảng

Tạo các thư mục output riêng ngoài Input rồi đặt biến môi trường, ví dụ PowerShell:

```powershell
$env:SM_CHANNEL_TRAIN = (Resolve-Path '.\my-input').Path
$env:SM_MODEL_DIR = "$PWD\my-run\model"
$env:SM_OUTPUT_DIR = "$PWD\my-run\output"
$env:MLOPS_WORK_DIR = "$PWD\my-run\work"
python "$env:SM_CHANNEL_TRAIN\train.py"
# Hoặc --config configs/experiment.json (mọi đường dẫn dữ liệu vẫn tính từ Input).
```

Model output phải trống; mỗi lần chạy dùng bộ thư mục mới. Không đặt output
trong Input. Khi chạy ngoài nền tảng mà không có MLFLOW_TRACKING_URI, script chỉ
ghi JSON/model. Không sửa config sau khi job đã submit: clone/retry để tạo job mới.

```powershell
python -m pytest models/nids-xgboost/training/tests -q
python -m ruff check models/nids-xgboost/training
```

Test dùng dữ liệu tổng hợp và mock tracking/GPU; không thay dataset/model v1/v2
hay kết quả nghiên cứu. Cần nghiệm thu riêng Docker CPU và NVIDIA GPU thực tế;
unit tests không chứng minh CUDA chạy được trên host hoặc production.

### Nghiệm thu local ngày 12/11/2026

- 37 tests đạt; Ruff và kiểm tra whitespace đạt.
- Chạy script bằng CLI không arguments trong image training-runner Python
  3.10.21 với đúng dependencies đã pin, Input mount read-only, giới hạn 1.5 vCPU
  và 2 GiB RAM. Trainer chọn một thread theo quota.
- CPU và một GPU NVIDIA GeForce GTX 1650 đều hoàn thành trên mẫu 400 dòng lấy
  từ train_2_classes.csv (200 BENIGN, 200 DDoS). Đây là smoke test tích hợp,
  không phải phép đo chất lượng nghiên cứu trên toàn dataset.
- Xác nhận Input từ chối ghi, Work ghi được, runner thu metadata và tạo archive.
- MLflow SDK 3.11.1 gửi create/log-batch đúng route, run ID, token và step tới
  HTTP server giả lập, không sử dụng Control Plane database thật.
- Model-packager hiện tại security-scan/load được model.joblib, xuất flavor
  XGBoost và load lại bằng MLflow PyFunc với class IDs khớp model gốc.

Chưa chạy vòng đời job đầy đủ qua UI/API, S3 và queue; chưa nghiệm thu trên
Kubernetes/T4/A10G. Không triển khai cluster hoặc thay đổi dữ liệu ứng dụng.
