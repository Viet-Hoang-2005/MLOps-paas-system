# Đánh giá hai case study cho đề tài KLTN MLOps/Continuous Training

> **Mục đích:** Đánh giá mức độ phù hợp của hai case study với hướng nghiên cứu về **label-efficient degradation verification** và **budget-aware Continuous Training (CT)**.
>
> **Ngày cập nhật:** 2026-09-17

## 1. Bối cảnh nghiên cứu

Định hướng KLTN xoay quanh câu hỏi:

> Khi một mô hình ML trong production có dấu hiệu suy giảm nhưng nhãn thực tế bị giới hạn, hệ thống có thể xác minh degradation và quyết định Continuous Training một cách an toàn, tiết kiệm nhãn như thế nào?

Điểm cần giữ rõ:

```text
Drift ≠ Degradation ≠ Retraining Trigger
```

Pipeline:

```text
Production / Replay
        ↓
Predictions + Feedback
        ↓
Drift + Quality Estimation
        ↓
Evidence Window
        ↓
Degradation Verification
        ↓
Budget-aware CT Policy
        ↓
KEEP / REQUEST_LABELS / HOLD / RETRAIN
        ↓
Training
        ↓
Independent Evaluation Gate
        ↓
Promote / Reject / Rollback
```

Hai case study:
1. **ML: Diabetes 130-US Hospitals – 30-day readmission**
2. **DL: Credit Card Fraud Detection**

Hai case **không nên trở thành hai đề tài riêng**. Nên dùng chung framework CT/policy và thay đổi workload, dataset, model.

## 2. Case Study 1 — Diabetes Readmission

### 2.1 Dataset

Dataset **Diabetes 130-US Hospitals for Years 1999–2008** của UCI chứa dữ liệu từ 10 năm chăm sóc lâm sàng tại 130 bệnh viện/mạng lưới y tế ở Mỹ. Mỗi record là một lần nhập viện của bệnh nhân được chẩn đoán tiểu đường, với thời gian nằm viện 1–14 ngày. Mục tiêu là dự đoán tái nhập viện trong vòng 30 ngày. Dataset gốc có khoảng **101,766 instances** và **47 features**. 

Phiên bản Fairlearn dùng cho tutorial SciPy 2021 được tiền xử lý thành binary classification; target biểu diễn việc tái nhập viện trong vòng 30 ngày và phiên bản này có **101,766 samples, 24 input features**.

### 2.2 Điểm mạnh

- Phù hợp với limited-label verification.
- Tabular ML, dễ chạy CPU.
- Có dữ liệu lịch sử dài, thuận lợi để xây replay stream.
- Có thể nghiên cứu degradation tổng thể và subgroup.
- Có ý nghĩa nghiệp vụ/y tế rõ ràng.

### 2.3 Điểm yếu / rủi ro

- Không phải production stream thực; cần replay harness và hidden labels.
- Concept drift cần được mô phỏng có kiểm soát.
- Fairness dễ làm scope phình to.

**Khuyến nghị:** fairness chỉ là secondary analysis, không phải research question chính.

## 3. Case Study 2 — Credit Card Fraud Detection

### 3.1 Dataset

Dataset **Credit Card Fraud Detection** có **284,807 transactions**, trong đó **492 fraud transactions**, tương đương khoảng **0.172%**. Dữ liệu gồm các biến số được PCA/anonymization cùng `Time`, `Amount`, `Class`, được thu thập trong hai ngày tháng 9/2013 từ European cardholders.

Keras có example chính thức về **imbalanced classification: credit card fraud detection**, phù hợp để làm workload DL.

### 3.2 Điểm mạnh

Fraud đặc biệt phù hợp với research core:

```text
Rare event
    +
Limited labels
    +
Uncertain quality
    +
Verification cost
    ↓
Need budget-aware evidence collection
```

Nếu lấy sample nhỏ để verify, sample random có thể chứa rất ít hoặc **không có fraud labels**. Điều này tạo ra một bài toán thực nghiệm rất phù hợp:

> Với cùng một label budget, policy nào xác minh degradation đáng tin cậy hơn?

### 3.3 Label budget

Nên theo dõi cả:

```text
number of labels
+
number of positive/fraud labels
```

và enforce:

```text
B_verify + B_train + B_gate ≤ B_total
```

### 3.4 Metric

Không nên dùng accuracy làm metric chính. Nên dùng:

- Precision
- Recall
- F1
- PR-AUC / AUPRC
- False Negative Rate
- False Positive Rate
- Calibration / Brier score nếu cần
- Number of fraud labels obtained
- Label cost

## 4. So sánh

| Tiêu chí | Diabetes | Fraud |
|---|---:|---:|
| Tabular ML | ★★★★★ | ★★★★★ |
| Deep Learning | ★★☆☆☆ | ★★★★★ |
| Class imbalance | ★★★☆☆ | ★★★★★ |
| Limited labels | ★★★★☆ | ★★★★★ |
| Drift simulation | ★★★★☆ | ★★★★★ |
| Performance degradation | ★★★★☆ | ★★★★★ |
| Fairness analysis | ★★★★★ | ★☆☆☆☆ |
| Interpretability | ★★★★☆ | ★★☆☆☆ |
| Business meaning | ★★★★★ | ★★★★☆ |
| Rare-event behavior | ★★★☆☆ | ★★★★★ |
| CPU-friendly | ★★★★★ | ★★★★☆ |
| DL demonstration | ★★☆☆☆ | ★★★★★ |
| CT fit | ★★★★☆ | ★★★★★ |
| 4-month feasibility | ★★★★★ | ★★★★☆ |
| Research potential | ★★★★★ | ★★★★★ |

> Các mức sao là **đánh giá thiết kế nghiên cứu**, không phải ranking chất lượng dataset/model trong thực tế.

## 5. Vai trò đề xuất

### Primary case: Fraud Detection

Lợi thế chính:

```text
Extreme imbalance
        +
Rare positive labels
        +
Limited verification budget
        +
Quality uncertainty
        ↓
Strong testbed for label-efficient degradation verification
```

### Secondary case: Diabetes Readmission

Dùng để kiểm tra generalization:

```text
Different domain
+
Tabular ML
+
Different distribution characteristics
+
Optional subgroup analysis
        ↓
Generalization case
```

## 6. Không xây hai pipeline riêng

Nên có:

```text
                    ┌── Fraud Detection
                    │
Common CT Framework ┤
                    │
                    └── Diabetes Readmission
```

Dùng chung:
- Evidence Window
- Drift Detector
- CBPE / ATC
- Label Request
- Label Budget
- Verification Engine
- Decision Policy
- Training Orchestrator
- Evaluation Gate
- Replay Harness
- Metrics
- Experiment runner

Chỉ thay đổi:
- Dataset
- Model
- Feature schema
- Quality metrics
- Scenario parameters

## 7. Experimental Scenarios

### S0 — Stable

Không có degradation đáng kể.

Mục tiêu: đo false retraining / unnecessary retraining.

Expected:

```text
KEEP
```

### S1 — Covariate Shift

```text
P(X) changes
P(Y|X) ≈ stable
```

Mục tiêu: kiểm tra **drift ≠ degradation**.

### S2 — Harmful Drift

```text
P(X) changes
Performance ↓
```

Expected:

```text
REQUEST_LABELS
        ↓
VERIFY
        ↓
RETRAIN
```

### S3 — Performance / Calibration Degradation

```text
Input distribution ≈ stable
Performance ↓
```

Mục tiêu: chứng minh drift-only không đủ.

### S4 — Limited Labels

```text
Hidden labels
     ↓
Budget B
     ↓
Policy chooses what to reveal
```

Đây là scenario chính.

### S5 — Mixed Degradation

```text
Drift
+
Quality degradation
+
Limited labels
+
Budget constraint
```

Đây có thể là scenario end-to-end quan trọng nhất.

## 8. Baselines

### B0 — Static

Không retrain.

### B1 — Drift-only

```text
Drift detected
      ↓
RETRAIN
```

Dùng để kiểm tra drift ≠ degradation.

### B2 — Estimator-only

Dùng CBPE/ATC nhưng không có adaptive verification policy.

### B3 — Periodic Labeling

Định kỳ lấy labels với budget cố định.

### B4 — Proposed Policy

```text
Drift
+
Estimated degradation
+
Uncertainty
+
Label budget
        ↓
Decision
```

### B5 — Full-label Oracle

Cho access full ground truth để tạo reference/upper bound cho evaluation.

## 9. Metrics

### 9.1 Quality

- Precision
- Recall
- F1
- PR-AUC
- Calibration

### 9.2 Detection / Verification

- Degradation Detection Rate
- Missed Degradation Rate
- False Trigger Rate
- Verification Accuracy

### 9.3 CT Efficiency

- Number of Retraining Runs
- Unnecessary Retraining Rate
- Recovery Time
- Time-to-Retraining

### 9.4 Label Efficiency

Đây là nhóm quan trọng nhất:

- Total labels consumed
- Verification labels
- Training labels
- Gate labels
- Positive labels obtained
- Cost per verified degradation

Nên normalize:

```text
r = B_labels / N_production
```

### 9.5 Safety / Governance

- Budget violation rate
- Unsafe promotion rate
- Evaluation Gate failure rate
- Decision trace completeness
- Duplicate maintenance execution
- Recovery after worker failure

## 10. Label Pools

Không nên trộn toàn bộ labels.

```text
                    Total Label Budget B
                           │
             ┌─────────────┼─────────────┐
             ↓             ↓             ↓
        Verification    Training       Gate
           Pool           Pool          Pool
```

Enforce:

```text
B_verify + B_train + B_gate ≤ B
```

## 11. Evaluation Gate

```text
Training
   ↓
Candidate
   ↓
Independent Holdout
   ↓
Evaluation Gate
   ↓
PROMOTE / REJECT
```

Gate không được sử dụng cùng dữ liệu đã dùng cho verification/training/policy tuning để tránh optimistic bias.

## 12. Replay Harness

Nên implement sớm:

```text
Historical dataset
      ↓
Temporal / synthetic batches
      ↓
Production predictions
      ↓
Hidden labels
      ↓
Scenario injection
      ↓
Policy decisions
      ↓
Training / Gate
      ↓
Metrics
```

Replay phải deterministic để experiment reproducible.

## 13. Fraud-specific consideration

Với fraud rate khoảng 0.172%, sample nhỏ có thể cho:

```text
n labels = 100
fraud labels = 0
```

Do đó verification engine nên theo dõi:

```text
sample size
+
positive count
+
confidence interval / uncertainty
```

Không nên chỉ dựa vào một point estimate như `estimated F1 = x`.

## 14. Diabetes-specific consideration

Có thể bổ sung:

```text
Overall performance
        +
Group-specific performance
```

nhưng fairness nên là secondary analysis, không phải contribution chính.

## 15. Kiến trúc experiment

```text
                    ┌─────────────────────┐
                    │ Historical Dataset  │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │   Replay Harness    │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Production Batches  │
                    └──────────┬──────────┘
                               ↓
                 ┌─────────────┴─────────────┐
                 ↓                           ↓
          Drift Detection             Predictions
                 │                           │
                 └─────────────┬─────────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Evidence Window     │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ CBPE / ATC /         │
                    │ Verification Engine  │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ CT Decision Policy   │
                    └──────────┬──────────┘
                               ↓
              ┌────────────────┼────────────────┐
              ↓                ↓                ↓
            KEEP        REQUEST_LABELS        RETRAIN
                               │                │
                               └───────┬────────┘
                                       ↓
                                Training Pipeline
                                       ↓
                                Candidate Model
                                       ↓
                                Evaluation Gate
                                       ↓
                              Promote / Reject
                                       ↓
                                    Metrics
```

## 16. Mapping vào repository

Nên tách research layer:

```text
research/
├── replay/
│   ├── stream.py
│   ├── scenarios.py
│   └── hidden_labels.py
├── policies/
│   ├── static.py
│   ├── drift_only.py
│   ├── estimator_only.py
│   ├── periodic_labeling.py
│   ├── proposed.py
│   └── oracle.py
├── experiments/
│   ├── run_experiment.py
│   ├── run_ablation.py
│   └── configs/
├── metrics/
│   ├── quality.py
│   ├── detection.py
│   ├── label_cost.py
│   ├── retraining.py
│   └── safety.py
└── results/
```

Production platform giữ các thành phần hiện có:

```text
services/control-plane/
services/model-serving/
training/
deploy/
observability/
terraform/
ansible/
gitops/
```

Không cần rebuild model serving, model registry, training engine, drift detector, Kubernetes, Terraform/Ansible, Kafka/Redpanda, MLflow.

## 17. Scope khóa cho KLTN 4 tháng

### Must-have

- [ ] Fraud dataset
- [ ] Diabetes dataset
- [ ] Replay Harness
- [ ] Hidden-label mechanism
- [ ] Evidence Window
- [ ] Label Budget
- [ ] Label Request / Feedback
- [ ] CBPE / ATC
- [ ] Verification engine
- [ ] CT Decision Policy
- [ ] Training integration
- [ ] Independent Evaluation Gate
- [ ] Baselines
- [ ] Controlled scenarios
- [ ] Metrics
- [ ] Ablation
- [ ] Reproducible experiment

### Should-have

- [ ] CT observability
- [ ] Idempotency tests
- [ ] Worker failure injection
- [ ] Reconciliation
- [ ] Argo/Kubernetes end-to-end validation
- [ ] Diabetes subgroup analysis

### Không nên thêm

- LLM
- Incremental learning
- Pseudo-labeling
- Causal inference
- Advanced HPO
- Multi-model research
- Multi-GPU research
- Multi-region HA
- Autoscaling research
- Research question riêng về fairness

## 18. Kết luận

Cấu hình khuyến nghị:

| Thành phần | Lựa chọn |
|---|---|
| Primary workload | Credit Card Fraud Detection |
| Secondary workload | Diabetes Readmission |
| Primary research problem | Label-efficient degradation verification |
| CT contribution | Budget-aware decision policy |
| ML workload | Diabetes |
| DL workload | Fraud |
| Main rare-event test | Fraud |
| Main subgroup/fairness test | Diabetes |
| Main infrastructure | Existing MLOps repo |
| Research execution | Replay Harness |
| Ground truth | Hidden during replay |
| Verification | CBPE/ATC + selective labels |
| Decision | KEEP / REQUEST_LABELS / HOLD / RETRAIN |
| Training | Existing training pipeline |
| Candidate safety | Independent Evaluation Gate |
| Main comparison | Static / Drift-only / Estimator-only / Periodic / Proposed / Oracle |
| Main constraint | `B_verify + B_train + B_gate ≤ B` |

Cách đóng góp khoa học nên được diễn đạt ở mức có thể kiểm chứng bằng experiment:

> **A framework for label-efficient degradation verification and budget-aware Continuous Training, evaluated across a rare-event deep-learning workload and a tabular healthcare machine-learning workload.**

Không nên claim rằng phương pháp là “optimal” hoặc áp dụng tốt cho mọi hệ thống ML. Nên đánh giá bằng các trade-off cụ thể: khả năng phát hiện degradation, missed degradation, unnecessary retraining, label consumption, recovery time và safety của promotion.
