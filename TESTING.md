# Hướng Dẫn Kiểm Thử & Nghiệm Thu Hệ Thống — MLOps PaaS

Tài liệu này cung cấp hướng dẫn toàn diện về chiến lược kiểm thử, các cổng kiểm soát chất lượng (Quality Gates), và quy trình nghiệm thu luồng nghiệp vụ từ đầu đến cuối (End-to-End Verification) của nền tảng **MLOps PaaS**.

---

## Mục lục

- [1. Chiến Lược Kiểm Thử (Testing Strategy)](#1-chiến-lược-kiểm-thử-testing-strategy)
- [2. Cổng Kiểm Soát Chất Lượng Mã Nguồn (Quality Gates)](#2-cổng-kiểm-soát-chất-lượng-mã-nguồn-quality-gates)
  - [2.1. Backend Linting (Ruff)](#21-backend-linting-ruff)
  - [2.2. Frontend Linting & Build (ESLint / TypeScript)](#22-frontend-linting--build-eslint--typescript)
  - [2.3. Infrastructure Validation (Terraform & Ansible)](#23-infrastructure-validation-terraform--ansible)
- [3. Kiểm Thử Đơn Vị & Tích Hợp Backend (Unit & Integration Tests)](#3-kiểm-thử-đơn-vị--tích-hợp-backend-unit--integration-tests)
  - [3.1. Nguyên tắc cô lập (Isolation Rules)](#31-nguyên-tắc-cô-lập-isolation-rules)
  - [3.2. Lệnh kiểm thử cho từng dịch vụ](#32-lệnh-kiểm-thử-cho-từng-dịch-vụ)
  - [3.3. Kiểm thử đặc thù cho Django Control Plane](#33-kiểm-thử-đặc-thù-cho-django-control-plane)
- [4. Kiểm Thử Tự Động Khai Báo Kubernetes & GitOps (K8s Offline Validation)](#4-kiểm-thử-tự-động-khai-báo-kubernetes--gitops-k8s-offline-validation)
- [5. Nghiệm Thu Vận Hành Hệ Thống Toàn Diện (End-to-End Verification)](#5-nghiệm-thu-vận-hành-hệ-thống-toàn-diện-end-to-end-verification)
  - [Giai đoạn 1: Xác nhận sức khỏe hạ tầng K3s & Edge ALB](#giai-đoạn-1-xác-nhận-sức-khỏe-hạ-tầng-k3s--edge-alb)
  - [Giai đoạn 2: Kiểm thử luồng Upload & Đóng gói Container Image](#giai-đoạn-2-kiểm-thử-luồng-upload--đóng-gói-container-image)
  - [Giai đoạn 3: Kiểm thử luồng Suy luận Phục vụ Mô hình (Serving & Inference)](#giai-đoạn-3-kiểm-thử-luồng-suy-luận-phục-vụ-mô-hình-serving--inference)
  - [Giai đoạn 4: Kiểm thử luồng Huấn luyện Cô lập (Training Sandbox Smoke Test)](#giai-đoạn-4-kiểm-thử-luồng-huấn-luyện-cô-lập-training-sandbox-smoke-test)
  - [Giai đoạn 5: Kiểm thử Giám sát Trôi dạt Dữ liệu & Tái huấn luyện Tự động](#giai-đoạn-5-kiểm-thử-giám-sát-trôi-dạt-dữ-liệu--tái-huấn-luyện-tự-động)
  - [Giai đoạn 6: Kiểm tra Khả năng Quan sát (Observability Dashboards)](#giai-đoạn-6-kiểm-tra-khả-năng-quan-sát-observability-dashboards)

---

## 1. Chiến Lược Kiểm Thử (Testing Strategy)

Hệ thống áp dụng mô hình kim tự tháp kiểm thử nhằm đảm bảo tính ổn định, độ tin cậy và ngăn ngừa lỗi hồi quy (regressions):

```
                     / \
                    /   \
                   / E2E \       --> Kiểm thử luồng nghiệp vụ trên cụm thật
                  /-------\
                 /  K8s    \     --> Kiểm định khai báo GitOps, CRDs, Sync Waves
                / Manifests \
               /-------------\
              /  Integration  \  --> Kiểm thử tương tác giữa các module nội bộ
             /-----------------\
            /    Unit Tests     \--> Kiểm thử logic nghiệp vụ cô lập (Mock 100%)
           /---------------------\
```

---

## 2. Cổng Kiểm Soát Chất Lượng Mã Nguồn (Quality Gates)

Toàn bộ mã nguồn phải vượt qua các công cụ kiểm tra tĩnh (Static Code Analysis) trước khi tạo Pull Request hoặc kích hoạt pipeline CI/CD.

### 2.1. Backend Linting (Ruff)

Hệ thống sử dụng **Ruff** cho toàn bộ các dịch vụ Python với cấu hình chuẩn hóa tại `services/ruff.toml`:

```bash
# Cài đặt công cụ lint
pip install -r services/requirements-lint.txt

# Kiểm tra linting cho toàn bộ thư mục backend
python -m ruff check services/

# Tự động sửa các lỗi format an toàn
python -m ruff check --fix services/
```

### 2.2. Frontend Linting & Build (ESLint / TypeScript)

Thực hiện từ thư mục `web/`:

```bash
cd web/

# Kiểm tra quy chuẩn mã nguồn và TypeScript types
pnpm lint

# Kiểm tra tính toàn vẹn của tiến trình build đóng gói
pnpm build
```

### 2.3. Infrastructure Validation (Terraform & Ansible)

#### Kiểm tra Terraform:
```bash
cd infra/
terraform fmt -check -recursive
terraform validate
```

#### Kiểm tra Ansible:
```bash
cd ansible/
export ANSIBLE_CONFIG=./ansible.cfg
ansible-playbook -i inventory/terraform.py site.yml --syntax-check
ansible-lint .
```

---

## 3. Kiểm Thử Đơn Vị & Tích Hợp Backend (Unit & Integration Tests)

### 3.1. Nguyên tắc cô lập (Isolation Rules)

> [!IMPORTANT]
> **Quy Tắc Vàng Kiểm Thử Backend:**
> - Tuyệt đối **không gọi tới cơ sở dữ liệu thật, Redis thật, Redpanda, S3, Docker daemon, Harbor hay Kubernetes cluster** trong các bài kiểm thử đơn vị.
> - Toàn bộ các kết nối ngoại vi phải được thay thế bằng pytest fixtures, `unittest.mock.Mock` / `AsyncMock`, `tmp_path`, hoặc `InMemoryStorage`.
> - Mỗi bài test phải độc lập, tự dọn sạch môi trường và không để rò rỉ trạng thái sang bài test kế tiếp.
> - Pipeline CI áp dụng ngưỡng chặn độ bao phủ mã nguồn (**Code Coverage $\ge$ 70%**).

---

### 3.2. Lệnh kiểm thử cho từng dịch vụ

Bạn có thể chạy kiểm thử cho từng dịch vụ riêng biệt bằng cách di chuyển vào thư mục tương ứng:

```bash
# 1. Consumer Worker (Kiểm thử micro-batching, outbox retry, Kafka lifecycle)
cd services/consumer
python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=70

# 2. Model Server Gateway (Kiểm thử verify JWT/JWKS, routing URL, telemetry)
cd services/model-server
python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=70

# 3. Machine Learning Serving (Kiểm thử nạp artifact MLflow, xếp cột đặc trưng, predict_proba)
cd services/machine-learning-serving
python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=70

# 4. Deep Learning Serving (Kiểm thử BentoML service, tensor normalization, fault tolerance)
cd services/deep-learning-serving
python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=70

# 5. Model Packager (Kiểm thử flavor detection, Kaniko 3-step payload, TarSlip protection)
cd services/model-packager
python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=70

# 6. Training Runner (Kiểm thử sandbox subprocess, METRIC_JSON parser, process group cleanup)
cd services/training-runner
python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=70

# 7. Evidently AI (Kiểm thử kiểm định K-S test, xuất 3 file báo cáo, guard checks)
cd services/evidently
python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=70
```

---

### 3.3. Kiểm thử đặc thù cho Django Control Plane

Control Plane chứa 10 domain apps và cấu hình cơ sở dữ liệu quan hệ, do đó cần thực hiện thêm các bước kiểm tra đặc thù của Django:

```bash
cd services/control-plane

# 1. Kiểm tra tính toàn vẹn của cấu hình Django
python manage.py check --settings=config.settings.test

# 2. Kiểm tra phát hiện xung đột hoặc thiếu file migration (Dry-run)
python manage.py makemigrations --check --dry-run --settings=config.settings.test

# 3. Chạy toàn bộ bộ kiểm thử đơn vị với In-memory SQLite và Eager Celery
python -m pytest
```

---

## 4. Kiểm Thử Tự Động Khai Báo Kubernetes & GitOps (K8s Offline Validation)

Thư mục `k8s/validate/tests/` chứa bộ kiểm thử tự động phân tích tĩnh (Static Manifest & Policy Validation) được viết bằng Python/Pytest để kiểm tra toàn bộ 5 mặt phẳng GitOps trước khi đồng bộ lên cụm K3s.

Thực thi từ thư mục gốc của repository:
```bash
# Trên Windows PowerShell:
$env:PYTHONPATH="."; pytest k8s/validate/tests/ -v

# Trên Linux / macOS / WSL:
PYTHONPATH="." pytest k8s/validate/tests/ -v
```

Bộ test tự động xác nhận 14 tiêu chí kỹ thuật:
1. Xác thực tính nhất quán của Kustomize Overlays.
2. Kiểm tra tài nguyên và giới hạn CPU/RAM (Cluster Capacity).
3. Kiểm tra an toàn thực thi và phân quyền ServiceAccounts.
4. Xác minh nguồn gốc Helm Charts đáng tin cậy.
5. Kiểm tra cấu hình cụm Redis Sentinel High Availability.
6. Xác minh quyền sở hữu tài nguyên theo ranh giới tin cậy (Trust Boundaries).
7. Kiểm tra cấu hình thu thập nhật ký Loki và Alloy.
8. Xác thực cấu hình ExternalSecrets và tích hợp AWS Secrets Manager.
9. Kiểm định chính sách bảo mật chuỗi cung ứng (Kyverno Cosign verification).

---

## 5. Nghiệm Thu Vận Hành Hệ Thống Toàn Diện (End-to-End Verification)

Quy trình 6 giai đoạn nhằm nghiệm thu toàn bộ luồng hoạt động thực tế trên môi trường sản xuất K3s:

### Giai đoạn 1: Xác nhận sức khỏe hạ tầng K3s & Edge ALB

Truy cập SSH vào Master node:
```bash
# 1. Kiểm tra các node trong cụm (Master và Workers phải Ready)
sudo k3s kubectl get nodes -L workload-type

# 2. Kiểm tra tình trạng đồng bộ của toàn bộ 5 mặt phẳng GitOps (Tất cả phải Synced & Healthy)
sudo k3s kubectl get applications -n argocd \
  -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status

# 3. Đảm bảo không có Pod nào bị CrashLoopBackOff hoặc Error
sudo k3s kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded

# 4. Kiểm tra cụm PostgreSQL HA CloudNativePG (Phải có 1 Primary và 1 Standby sẵn sàng)
sudo k3s kubectl get clusters.postgresql.cnpg.io -A

# 5. Kiểm tra chính sách xác thực ảnh Kyverno
sudo k3s kubectl get clusterpolicy verify-platform-images
```

---

### Giai đoạn 2: Kiểm thử luồng Upload & Đóng gói Container Image

1. Đăng nhập vào Web Dashboard: `https://mlops-nids-nt114.id.vn`.
2. Truy cập vào dự án học máy $\rightarrow$ Chọn **Upload Model**.
3. Tải lên file trọng số mô hình mẫu (ví dụ `model.pkl` hoặc `model.pt`).
4. Nhấn **Build Model**:
   - Theo dõi log build thời gian thực được stream từ Redis hiển thị trên giao diện.
   - Kiểm tra trên K3s: Pod `model-packager` được kích hoạt và Kaniko thực hiện build rootless.
5. Sau khi build thành công, xác nhận:
   - Ảnh container mới xuất hiện trên Harbor Registry: `image-{project_id}:build-{build_id}`.
   - Phiên bản mới `v1` được đăng ký tự động vào **Model Registry**.

---

### Giai đoạn 3: Kiểm thử luồng Suy luận Phục vụ Mô hình (Serving & Inference)

1. Nhấn nút **Deploy** cho phiên bản mô hình vừa tạo trên Dashboard.
2. Kiểm tra trên cụm K3s: Pod phục vụ suy luận (`machine-learning-serving` hoặc `deep-learning-serving`) được tạo trong namespace `mlops-model-runtimes`.
3. Gửi yêu cầu dự đoán thử nghiệm qua cổng Ingress ALB tới `model-server` Gateway:

```bash
curl -X POST https://api.mlops-nids-nt114.id.vn/models/<model_version_id>/predict \
  -H "Authorization: Bearer <your_jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "features": {
      "Destination_Port": 80,
      "Flow_Duration": 1200,
      "Total_Fwd_Packets": 10,
      "Total_Backward_Packets": 8
    }
  }'
```

4. Xác nhận:
   - Phản hồi HTTP 200 trả về nhãn dự đoán (`prediction`) và điểm tin cậy (`confidence`) với độ trễ $< 20\text{ ms}$.
   - Sự kiện suy luận được `model-server` đẩy vào Redpanda Kafka topic `mlops_paas_production_data`.
   - Worker `consumer` tiêu thụ sự kiện và ghi bản ghi vào bảng `production_predictionrecord`.

---

### Giai đoạn 4: Kiểm thử luồng Huấn luyện Cô lập (Training Sandbox Smoke Test)

Thực hiện kiểm thử huấn luyện tự động trong môi trường sandbox K3s thông qua Ansible:

```bash
cd ansible/
ansible-playbook -i inventory/terraform.py site.yml --tags platform-training \
  -e deploy_training_platform=true
```

Quy trình xác minh:
1. Kubeflow Training Operator khởi chạy `PyTorchJob` trong namespace tạm thời `ansible-training-smoke`.
2. Worker tải dữ liệu qua Presigned S3 URLs, thực thi huấn luyện và ghi log `METRIC_JSON`.
3. Gói `training_output.zip` được đẩy lên S3 và gọi webhook callback về Control Plane.
4. Sau khi hoàn thành, namespace tạm thời tự động bị dọn dẹp sạch sẽ và Karpenter thu hồi node nhàn rỗi.

---

### Giai đoạn 5: Kiểm thử Giám sát Trôi dạt Dữ liệu & Tái huấn luyện Tự động

1. Tạo một bộ giám sát `DriftMonitor` trên giao diện gắn với tập dữ liệu tham chiếu (Reference Dataset).
2. Kích hoạt phân tích trôi dạt thủ công hoặc chờ `consumer` tích lũy đủ số mẫu:
   ```bash
   curl -X POST https://api.mlops-nids-nt114.id.vn/api/drift-monitors/<monitor_id>/runs/ \
     -H "Authorization: Bearer <your_jwt_token>"
   ```
3. Quan sát pod `evidently` thực thi kiểm định thống kê Kolmogorov-Smirnov và Chi-square.
4. Truy cập giao diện để xem báo cáo trực quan **HTML Interactive Report**.
5. **Kiểm thử Continuous Training (CT):** Khi tỷ lệ trôi dạt vượt ngưỡng (`drift_share > 0.6`), xác nhận module `apps.ct` tự động kích hoạt một `TrainingJob` mới để huấn luyện lại mô hình với dữ liệu sản xuất vừa thu thập.

---

### Giai đoạn 6: Kiểm tra Khả năng Quan sát (Observability Dashboards)

1. Truy cập **Grafana Dashboard**: `https://grafana.mlops-nids-nt114.id.vn`.
2. Kiểm tra các bảng điều khiển chuyên biệt:
   - **Model Serving Metrics:** RPS Throughput, P95/P99 Latency, tỷ lệ lỗi HTTP 4xx/5xx của từng worker pod.
   - **Redpanda / Kafka Metrics:** Tốc độ tiêu thụ tin nhắn và độ trễ hàng đợi (Consumer Group Lag).
   - **K3s Infrastructure Metrics:** Tỷ lệ chiếm dụng CPU, RAM và GPU vRAM của toàn cụm.
3. Kiểm tra **Grafana Loki**: Xác nhận log của các tác vụ huấn luyện và đóng gói được thu thập đầy đủ và có thể tra cứu nhanh chóng.
