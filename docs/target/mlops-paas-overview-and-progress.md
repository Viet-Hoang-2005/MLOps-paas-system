# Tổng quan hướng đi, Mục tiêu và Tiến độ Hiện tại của Hệ thống (KLTN)

> Tài liệu này tổng hợp định hướng nghiên cứu từ [System_Development_Summary.tex](file:///d:/AI%20Models/mlops-paas-system/graduate/target/summary/System_Development_Summary.tex) và [Continuous_Training_Case_Study.tex](file:///d:/AI%20Models/mlops-paas-system/graduate/target/case/Continuous_Training_Case_Study.tex), đồng thời đối chiếu trực tiếp với trạng thái mã nguồn hiện tại của repository (cập nhật ngày `26/11/2026`).

---

## 1. Tổng quan hướng đi Khóa luận Tốt nghiệp

### 1.1. Bài toán cốt lõi
Hệ thống MLOps PaaS hiện tại đã có các khối nền tảng (quản lý model, model serving, thu thập prediction qua Kafka/Redpanda, phát hiện drift với Evidently, training workspace, MLflow tracking, packaging, deployment và Kubernetes/GitOps). Hướng KLTN mở rộng nền tảng này thành một vòng **Continuous Training (CT) thích ứng với Data Drift dưới ngân sách gán nhãn hạn chế**, dựa trên nguyên tắc:

```text
Drift != Degradation != Retraining Trigger
```

- **Drift** chỉ cho biết phân phối đầu vào $P(X)$ hoặc đầu ra $P(\hat{Y})$ thay đổi.
- **Degradation** là sự suy giảm chất lượng thực tế của mô hình trên dữ liệu mục tiêu.
- **Retraining Trigger** là quyết định vận hành sau khi đã cân nhắc bằng chứng suy giảm, độ không chắc chắn của ước lượng và ngân sách nhãn còn lại.

### 1.2. Kiến trúc vòng CT khép kín
```text
Production / Replay ──► Predictions + Feedback ──► Drift + Quality Estimation (CBPE/ATC)
        │                                                       │
        ▼                                                       ▼
Independent Evaluation Gate ◄── Training ◄── Budget-aware Policy (KEEP / REQUEST_LABELS / HOLD / RETRAIN)
        │
        ▼
  PROMOTE / REJECT / ROLLBACK (giữ an toàn cho Champion)
```

Hệ thống tách biệt rõ hai lớp:
- **Production Layer (`services/`, `web/`, `terraform/`, `ansible/`, `argocd/`):** serving, registry, training engine, drift detector, Kafka/Redpanda, MLflow, packaging, deployment và CT control-plane orchestration.
- **Research Layer (`research/` - đang chuẩn bị xây dựng):** replay harness deterministic, scenario injection (`S0–S5`), hidden labels, cài đặt đối chứng policy (`B0–B5`), experiment runner và metrics benchmark.

---

## 2. Mục tiêu và Câu hỏi nghiên cứu

### 2.1. Câu hỏi nghiên cứu (Research Questions)
1. **RQ1 — Xác minh degradation với ít nhãn (Label-efficient degradation verification):**  
   Khi model trong production có dấu hiệu suy giảm và chỉ được cấp một ngân sách gán nhãn hữu hạn, policy nào xác minh degradation đáng tin cậy hơn các trigger đối chứng? Đo lường trade-off giữa *detection rate*, *missed degradation rate*, *unnecessary retraining*, *label consumption* và *recovery time*.
2. **RQ2 — An toàn và phục hồi của vòng CT (Safety & Recovery):**  
   Khi worker, workflow, callback, storage hoặc evaluation gate gặp sự cố ở các thời điểm khác nhau, hệ thống có bảo toàn được ngân sách nhãn, tránh tạo logical job trùng lặp, không cập nhật sai champion và vẫn giữ champion cũ phục vụ an toàn hay không?

### 2.2. Sáu mục tiêu kỹ thuật chính
1. Chuẩn hóa **prediction contract** gồm xác suất $0\text{--}1$, timestamp, model version, request ID, latency, threshold, calibration version và snapshot manifest.
2. Xây dựng **replay harness deterministic** với hidden labels và 6 kịch bản `S0–S5`.
3. Hoàn thiện **Evidence Window**, **CBPE/ATC quality estimator**, **Verification Engine**, **Label Request / Feedback** và **Label Budget Ledger** với ràng buộc độc lập 3 pool:
   $$B_{\text{verify}} + B_{\text{train}} + B_{\text{gate}} \le B_{\text{total}}$$
4. Thiết kế **Budget-aware Decision Policy (`B4`)** trả về `KEEP`, `REQUEST_LABELS`, `HOLD` hoặc `RETRAIN`, so sánh với các baseline `B0–B5`.
5. Kết nối quyết định policy với **Training Job → Build/Register → Independent Evaluation Gate** để promote, reject hoặc rollback candidate an toàn.
6. Thực nghiệm so sánh **B0–B5** trên **S0–S5** ở cả hai case study và chạy fault-injection cho RQ2.

### 2.3. Hai Case Study thực nghiệm
| Tiêu chí | Primary Case: Bank Account Fraud (BAF) | Secondary Case: Diabetes Readmission | Vai trò |
|---|---|---|---|
| **Model family** | Deep Learning — MLP PyTorch (2 hidden layers `128-64`, `BCEWithLogitsLoss`) | Tabular ML — `LogisticRegression` + `StandardScaler` | Kiểm tra framework CT trên cả 2 nhánh DL và ML |
| **Đặc điểm dữ liệu** | Rare-event (fraud hiếm), temporal theo tháng (`0–7`), variant thay đổi separability | Dữ liệu bệnh án (101,766 mẫu, 24 features sau tiền xử lý), nhãn tái nhập viện 30 ngày đến trễ | BAF là stress test chính (RQ1); Diabetes kiểm tra tổng quát hóa domain y tế |
| **Metrics chính** | PR-AUC (Average Precision), Recall, Precision, F1, FNR, FPR, Brier score, fraud labels thu được | Balanced Accuracy, ROC-AUC, Recall, FNR, Brier score (+ subgroup analysis phụ bằng Fairlearn `MetricFrame`) | Không gộp metric khác nghĩa giữa hai case |

> **Lưu ý phạm vi:** Bộ `models/nids-xgboost` (CICIDS2017) tiếp tục đóng vai trò *system validation workload* kiểm thử hạ tầng (serving, Kafka, drift, logging), không thay thế BAF/Diabetes trong kết quả RQ1. Phạm vi KLTN **không** mở rộng sang LLM, incremental learning, pseudo-labeling, causal inference, advanced HPO, multi-GPU hay fairness như một RQ độc lập.

### 2.4. Kịch bản (`S0–S5`) và Baselines (`B0–B5`)
- **Kịch bản:**
  - `S0`: Stable (đo false retraining, kỳ vọng `KEEP`).
  - `S1`: Covariate shift — $P(X)$ đổi nhưng $P(Y|X)$ ổn định (chứng minh drift $\ne$ degradation).
  - `S2`: Harmful drift — phân phối đổi và chất lượng giảm (xác minh rồi `RETRAIN`).
  - `S3`: Concept/calibration degradation dù input drift chưa rõ (chứng minh drift-only không đủ).
  - `S4`: Hidden labels với ngân sách hữu hạn (đánh giá selective verification).
  - `S5`: Drift + degradation + nhãn trễ + budget constraint (kịch bản end-to-end trọng tâm).
- **Baselines:**
  - `B0` Static (không retrain) | `B1` Drift-only | `B2` Estimator-only (CBPE/ATC, không adaptive policy) | `B3` Periodic labeling | `B4` Proposed budget-aware policy | `B5` Full-label oracle (upper bound).

---

## 3. Đánh giá Tiến độ Hệ thống Hiện tại (Cập nhật 26/11/2026)

So với thời điểm đánh giá trong `.tex` (`17/09/2026`), hệ thống đã tiến thêm nhiều bước quan trọng ở **tầng nền tảng PaaS**, **schema miền CT**, và **hai bộ workload case study**, nhưng **luồng nghiệp vụ CT khép kín và Research Layer** vẫn là phần cần tập trung hoàn thiện tiếp theo.

### 3.1. Bảng tổng hợp hiện trạng

| Hạng mục / Năng lực | Trạng thái | Chi tiết đã có trong Repo | Khoảng trống cần bổ sung |
|---|---|---|---|
| **1. Nền tảng MLOps PaaS Core** | **Hoàn thiện cao** | Đủ CRUD Project/Preview/Version, Training Workspace + Output Contract v2, MLflow Tracking 3.18, Model Packager, Serving Gateway (`model-server` + Traefik), ML/DL Serving, Kafka/Redpanda Consumer, Evidently Drift, Evolution & Monitoring UI (`web/`). Môi trường local hỗ trợ **MinIO (`cgr.dev/chainguard/minio`)** mặc định & tự chuyển AWS S3. | Chỉ bảo trì khi nối vào vòng CT. |
| **2. Data Contract Prediction (`production`)** | **Một phần** | Model [PredictionRecord](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/production/models.py#L6-L51) đã có sẵn `positive_class_probability` (check `0..1`), `class_mapping`, `decision_threshold` (check `0..1`), `calibration_version`, `latency_ms`, `request_id`; [consumer/src/database.py](file:///d:/AI%20Models/mlops-paas-system/services/consumer/src/database.py#L164) đã map các cột khi insert. | Serving engines (`machine-learning-serving`, `deep-learning-serving`, `model-server`) hiện chủ yếu trả/gửi `confidence` (%); cần chuẩn hóa emit đủ `positive_class_probability`, `decision_threshold`, `calibration_version`, `latency_ms` nhất quán cho cả BAF và Diabetes. |
| **3. Miền Continuous Training (`apps/ct`)** | **Có Schema DB (~30%)** | [apps/ct/models.py](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/ct/models.py) và migrations đã định nghĩa đầy đủ **11 bảng & DB constraints**: `MaintenancePolicy` (B0–B5), `DatasetSnapshot`, `EvidenceWindow`, `EvidenceWindowSample` (`hidden`/`verify`/`train`/`gate`), `LabelBudget` (check $B_{\text{verify}}+B_{\text{train}}+B_{\text{gate}}\le B_{\text{total}}$), `LabelRequest`, `LabelRequestItem`, `Feedback`, `LabelLedgerEntry` (reserve/commit/release), `MaintenanceDecision`, `MaintenanceRun` (1 active run/project), `MaintenanceStepAttempt`, `EvaluationGate` (`candidate != champion`). Đã nối cascade delete trong `catalog/services/deletion.py` và FK `EvidenceWindow` ở `drift/models.py`. Có [test_models.py](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/ct/tests/test_models.py). | **Chưa có `services/`, `api/` (endpoints/serializers), `tasks.py`** cho toàn bộ vòng CT: chưa có logic gom `EvidenceWindow`, cấp/thu hồi `LabelBudget`, CBPE/ATC estimator, Verification Engine, Policy `B0–B5`, điều phối `MaintenanceRun` & `EvaluationGate` runner. |
| **4. Case Study 2: Diabetes Readmission (`models/diabetes-logreg`)** | **Chạy được trên PaaS (~70%)** | Có [preprocess.py](file:///d:/AI%20Models/mlops-paas-system/models/diabetes-logreg/notebooks/preprocess.py), script huấn luyện trên MLOps PaaS ([train.py](file:///d:/AI%20Models/mlops-paas-system/models/diabetes-logreg/training/input/train.py), `config.json`, `feature_schema.json`), unit test (`test_train.py`), `artifacts/` (`fairness_report.json`, `metrics.json`, `model.joblib`...) và đã test **Training → Build → Deploy → Predict** thành công trên UI (`~62-66%` accuracy trên tập `class_weight="balanced"`). | Chưa có temporal/hospital replay script có hidden labels, chưa tách 3 pool độc lập cho CT và chưa nối subgroup analysis vào gate/báo cáo CT. |
| **5. Case Study 1: Bank Account Fraud (`models/baf-mlp`)** | **Có Baseline Training (~50%)** | Có notebooks BAF/CTGAN/variant, `artifacts/` (`model.pt`, `preprocessor.joblib`, `data_contract.json`, `split_manifest.json`), và [models/baf-mlp/training/kaggle/train.py](file:///d:/AI%20Models/mlops-paas-system/models/baf-mlp/training/kaggle/train.py) đã cài đặt chặt chẽ chia tháng `0–3` (train), `4` (val/threshold), `5` (reference), `6–7` (dành cho CT replay), PyTorch MLP (`BCEWithLogitsLoss`, early stopping PR-AUC) và đóng gói `model.tar.gz`. | Chưa đưa thành `training/input/` chuẩn để chạy mượt qua **MLOps PaaS Training Workspace + Model Packager + `deep-learning-serving`**, và chưa xác minh *prediction parity* giữa inference từ `deep-learning-serving` với model PyTorch gốc (do cần wrapper ghép `preprocessor.joblib` + `model.pt` + threshold). |
| **6. Evidence, CBPE/ATC & Drift (`services/evidently`)** | **Một phần (~40%)** | Đã có `DriftMonitor`, `DriftRun`, webhook automatic drift và trang Drift Monitoring/Report trên `web/`. | Chưa tích hợp bộ ước lượng chất lượng không cần nhãn (**CBPE / ATC**), chưa tách rõ Drift vs Estimated Degradation trong `EvidenceWindow`, chưa tự tạo `EvidenceWindow` từ stream/outbox. |
| **7. Independent Evaluation Gate & Champion Protection** | **Chưa có logic CT (~20%)** | Đã có model `EvaluationGate` trong DB, Alias/Version/Deployment trong `registry` & `deployment`, và health check container. | Chưa có pipeline đánh giá `candidate` vs `champion` trên `gate` snapshot holdout độc lập, chưa có tự động promote/reject/rollback gắn với `MaintenanceRun` và kiểm tra invariants. |
| **8. Research Layer (`research/` cho KLTN)** | **Chưa có (0% code CT)** | Thư mục `research/` hiện chỉ chứa bài báo & slide CSONET 2026 (nội dung drift-aware trước đó). | Chưa có `research/replay`, `research/policies` (`B0–B5`), `research/experiments` (runner `S0–S5`, ablation, fault injection), `research/metrics` và bộ kết quả tái lập theo seed/manifest. |
| **9. CT Observability & UI (`web/`)** | **Chưa có** | Có Evolution, Overview, Monitoring, Training, Deployment UI. | Chưa có giao diện xem `EvidenceWindow`, `LabelBudget` ledger, `MaintenanceDecision` trace, `MaintenanceRun` lineage và kết quả `EvaluationGate`. |
| **10. Hạ tầng Production & Fault-tolerance (K3s/Argo)** | **Một phần** | Có Terraform, Ansible, ArgoCD/Argo Workflows, Prometheus/Grafana và Docker Compose local hoàn chỉnh (kèm MinIO). | Chưa chạy end-to-end CT trên K3s/Argo và chưa làm chiến dịch fault injection (RQ2). |

### 3.2. Kết luận về vị trí hiện tại trên đường đua KLTN
- **Mặt mạnh:** Nền tảng MLOps PaaS (PaaS Core), schema dữ liệu miền CT (`apps/ct/models.py`, `PredictionRecord`), môi trường dev local ổn định (MinIO), và phần chuẩn bị dữ liệu/training cơ sở của cả **Diabetes** lẫn **BAF** đã sẵn sàng — rút ngắn rất nhiều công sức phần hạ tầng.
- **Trọng tâm quyết định thành công từ nay trở đi:**
  1. Đưa **BAF MLP PyTorch** chạy end-to-end trên MLOps PaaS với *prediction contract* chuẩn xác (`positive_class_probability`, `threshold`).
  2. Xây dựng lõi **Verification + Label Budget Ledger + Policy `B0–B5` + Independent Evaluation Gate** (vừa phục vụ `apps/ct` trên platform, vừa phục vụ `research/` replay harness deterministic).
  3. Hoàn tất thực nghiệm **`S0–S5` × `B0–B5`** trên BAF (chính) & Diabetes (phụ) và **fault injection (RQ2)**.
