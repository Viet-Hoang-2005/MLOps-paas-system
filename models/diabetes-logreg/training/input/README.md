# Diabetes-Logreg MLOps-PaaS Training

Script huấn luyện mô hình **Logistic Regression** (Scikit-learn) dự đoán nguy cơ bệnh nhân tiểu đường tái nhập viện trong vòng 30 ngày, tuân thủ hợp đồng Workspace & Output v2 của nền tảng **MLOps-PaaS**.

## Chuẩn bị dữ liệu (`training_data.csv` & `test_data.csv`)

Chạy script từ thư mục gốc repository để tiền xử lý dữ liệu thô `diabetic_data.csv` và tách đều 80% / 20% theo `patient_nbr` (`StratifiedGroupKFold(n_splits=5)`):

```powershell
python scripts/prepare_diabetes_data.py
```

Kết quả được xuất ra `models/diabetes-logreg/data/`:
- `training_data.csv` (80%): dùng làm dữ liệu huấn luyện trong workspace.
- `test_data.csv` (20%): dùng cho kiểm thử dự đoán (*Run prediction test*) và kiểm tra Data Drift (*Drift Monitoring*).

## Chạy trên nền tảng MLOps-PaaS

Tạo Training Job (hoặc Workspace), upload các file sau vào **Input**, chọn `train.py` làm entry point và chọn Framework **Scikit-learn**:

```text
Input/
├── train.py
├── requirements.txt
├── config.json
├── feature_schema.json
└── data/
    └── training_data.csv
```

Không cần cấu hình biến môi trường MLflow thủ công: nền tảng tự cấp tracking capability khi chạy.

## Outputs được tạo

```text
SM_MODEL_DIR/
  model.joblib
SM_OUTPUT_DIR/
  label_mapping.json
  input_schema.json
  metrics.json
  params.json
  feature_importance.json
  model_insights.json
  training_report.json
```

Khi gán vào Model Project (`Project assignment`), bạn có thể chọn `model.joblib` cùng 6 file JSON tương ứng (`label_mapping`, `input_schema`, `metrics`, `params`, `model_insights`, `feature_importance`). Nhãn trong `label_mapping.json` khớp trực tiếp với cột `Label` của `test_data.csv`:
- `"0"`: `"No Readmission within 30 Days"`
- `"1"`: `"Readmission within 30 Days"`

## Kiểm thử local

```powershell
python -m pytest models/diabetes-logreg/training/mlops-paas/tests -q
```
