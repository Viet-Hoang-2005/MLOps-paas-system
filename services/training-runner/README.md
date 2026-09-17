# Training Runner — Kubeflow PyTorchJob Container

Training Runner là container chạy bên trong **Kubeflow PyTorchJob** được tạo bởi Argo Workflows. Nó download code và data từ S3, thực thi training script của Tenant, đóng gói kết quả, và upload lên S3.

---

## Vai Trò

- **Environment Setup**: Download `source.zip` (code Tenant) và training data từ S3; cài đặt `requirements.txt` nếu có.
- **Script Execution**: Chạy entry point script của Tenant trong môi trường chuẩn với các biến môi trường SageMaker-compatible.
- **Metric Collection**: Thu thập metrics từ training script qua stdout parsing (`METRIC_JSON:{"accuracy": 0.95}`) hoặc file `SM_OUTPUT_DIR/metrics.json`.
- **Model Packaging**: Sau khi training hoàn tất, đóng gói toàn bộ `SM_MODEL_DIR` thành `model.tar.gz` và upload lên `S3_OUTPUT_URI`.
- **Metadata Bundle**: Ghi bundle metadata vào `SM_MODEL_DIR/_mlops/` để Control Plane tổng hợp thông tin.
- **Log Streaming**: Mọi log đều được ghi vào Redis (`training_logs:{job_id}`) để Frontend HTTP Polling hiển thị real-time.
- **MLflow Integration**: Log metrics và artifact vào MLflow nếu `MLFLOW_TRACKING_URI` được cung cấp.

---

## Biến Môi Trường (Inject bởi Argo Workflow)

| Biến | Mô tả |
|---|---|
| `S3_SOURCE_URI` | S3 URI của `source.zip` (code Tenant) |
| `S3_TRAINING_DATA_URI` | S3 URI của training data CSV |
| `S3_OUTPUT_URI` | S3 URI đích để upload `model.tar.gz` |
| `S3_JOB_SOURCE_BUNDLE_URI` | S3 URI của source bundle (optional) |
| `ENTRY_POINT` | Tên file entry point (vd: `train.py`) |
| `MODEL_VERSION` | Phiên bản model (vd: `v1`) |
| `TRAINING_JOB_ID` | ID của TrainingJob trên Control Plane |
| `TENANT_ID` | Tenant sở hữu job |
| `REQUIREMENTS_TEXT` | Nội dung requirements.txt (optional, inline) |
| `REDIS_URL` | Redis để stream training logs |
| `MLFLOW_TRACKING_URI` | MLflow server (optional) |
| `MLFLOW_EXPERIMENT_NAME` | Tên MLflow Experiment |
| `MLFLOW_ARTIFACT_ROOT` | S3 URI lưu MLflow artifacts |

---

## Biến Môi Trường cho Training Script của Tenant

Training script của Tenant **KHÔNG cần import MLflow**. Chỉ cần đọc:

| Biến | Giá trị |
|---|---|
| `SM_CHANNEL_TRAIN` | `/workspace/input/train` — thư mục chứa training data |
| `SM_MODEL_DIR` | `/workspace/model` — lưu model files tại đây |
| `SM_OUTPUT_DIR` | `/workspace/output` — lưu metrics, params |

---

## Cách Expose Metrics từ Training Script

```python
# Cách 1: Print JSON line
print(f"METRIC_JSON:{json.dumps({'accuracy': 0.95, 'loss': 0.12})}")

# Cách 2: Ghi file
import json, os
with open(os.path.join(os.environ['SM_OUTPUT_DIR'], 'metrics.json'), 'w') as f:
    json.dump({'accuracy': 0.95}, f)
```

---

## Metadata Bundle (SM_MODEL_DIR/_mlops/)

Sau training, Runner tự động tạo:

| File | Nội dung |
|---|---|
| `training_summary.json` | Tóm tắt job: duration, status, entry_point, model_version |
| `metrics.json` | Metrics cuối cùng từ training script |
| `params.json` | Hyperparameters từ `SM_OUTPUT_DIR/params.json` |
| `metric_events.jsonl` | Lịch sử metrics theo từng bước |
| `artifact_manifest.json` | Danh sách file trong `SM_MODEL_DIR` |
| `stdout.txt` / `stderr.txt` | Log đầy đủ của training script |
| `warnings.json` | Cảnh báo từ quá trình training |

---

## Cấu Trúc Thư Mục

```
services/training-runner/
└── src/
    ├── main.py         # Process entrypoint and exit-code handling
    ├── application.py  # Orchestrates one training job
    ├── config.py       # Required runtime configuration
    ├── io.py           # Presigned transfer, archive and requirements handling
    ├── metadata.py     # Metrics, insights, manifest and MLflow metadata helpers
    ├── resources.py    # cgroup resource sampling primitives
    └── execution.py    # Metric protocol and model archive handling
```

---

## Workspace Layout

```
/workspace/
├── source/            # Code Tenant (giải nén từ source.zip)
├── input/train/       # Training data (SM_CHANNEL_TRAIN)
├── model/             # Model output (SM_MODEL_DIR)
│   └── _mlops/        # Metadata bundle (tự động tạo bởi Runner)
└── output/            # Metrics, params (SM_OUTPUT_DIR)
```

---

## Build Local

```bash
docker build -f services/training-runner/Dockerfile -t mlops-paas-training-runner ./services/training-runner
```

---

## Ví dụ Training Script

Xem `examples/training/nids-xgboost/` để tham khảo training script mẫu tương thích với Training Runner.
