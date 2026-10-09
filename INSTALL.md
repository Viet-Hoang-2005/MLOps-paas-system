# Hướng Dẫn Cài Đặt & Vận Hành — MLOps PaaS

Tài liệu này cung cấp hướng dẫn chi tiết từng bước để thiết lập, triển khai và vận hành nền tảng **MLOps PaaS** trên cả 2 môi trường:
1. **Môi trường Cục bộ (Local Development):** Chạy nhanh thông qua Docker Compose (kết hợp S3 tùy chọn).
2. **Môi trường Sản xuất (Production K3s trên AWS):** Tự động hóa hoàn toàn từ hạ tầng đám mây (Terraform) $\rightarrow$ Cài đặt máy chủ & K3s (Ansible) $\rightarrow$ Quản trị ứng dụng khai báo (Argo CD GitOps).

---

## Mục lục

- [1. Triển khai Môi trường Cục bộ (Docker Compose)](#1-triển-khai-môi-trường-cục-bộ-docker-compose)
  - [1.1. Yêu cầu hệ thống](#11-yêu-cầu-hệ-thống)
  - [1.2. Các bước khởi chạy](#12-các-bước-khởi-chạy)
  - [1.3. Tùy chọn hạ tầng S3 AWS cho Local](#13-tùy-chọn-hạ-tầng-s3-aws-cho-local)
  - [1.4. Bảng tra cứu cổng và URL Local](#14-bảng-tra-cứu-cổng-và-url-local)
- [2. Triển khai Môi trường Sản xuất (Production K3s trên AWS)](#2-triển-khai-môi-trường-sản-xuất-production-k3s-trên-aws)
  - [2.1. Yêu cầu chuẩn bị](#21-yêu-cầu-chuẩn-bị)
  - [2.2. Bước 1: Khởi tạo hạ tầng AWS IaaS (Terraform)](#22-bước-1-khởi-tạo-hạ-tầng-aws-iaas-terraform)
  - [2.3. Bước 2: Đồng bộ bí mật lên AWS Secrets Manager](#23-bước-2-đồng-bộ-bí-mật-lên-aws-secrets-manager)
  - [2.4. Bước 3: Chuẩn bị máy chủ điều khiển Ansible (WSL / Linux)](#24-bước-3-chuẩn-bị-máy-chủ-điều-khiển-ansible-wsl--linux)
  - [2.5. Bước 4: Bootstrap K3s và khởi động GitOps Core (Ansible)](#25-bước-4-bootstrap-k3s-và-khởi-động-gitops-core-ansible)
  - [2.6. Bước 5: Xác minh trạng thái cụm K3s và Ingress Edge](#26-bước-5-xác-minh-trạng-thái-cụm-k3s-và-ingress-edge)
  - [2.7. Bảng tra cứu Production Service URLs](#27-bảng-tra-cứu-production-service-urls)
- [3. Gỡ cài đặt & Dọn dẹp Hạ tầng (Teardown & Cleanup)](#3-gỡ-cài-đặt--dọn-dẹp-hạ-tầng-teardown--cleanup)

---

## 1. Triển khai Môi trường Cục bộ (Docker Compose)

Chế độ này phù hợp cho việc phát triển tính năng, kiểm thử đơn vị và chạy thử nghiệm toàn bộ hệ sinh thái vi dịch vụ trên máy tính cá nhân.

### 1.1. Yêu cầu hệ thống

| Thành phần | Yêu cầu tối thiểu | Khuyến nghị |
|---|---|---|
| **Hệ điều hành** | Windows 10/11 (WSL2), macOS hoặc Linux | Ubuntu 22.04 LTS |
| **CPU / RAM** | 4 Cores / 8 GB RAM | 8 Cores / 16 GB RAM trở lên |
| **Docker Engine** | Docker v24.0+ & Docker Compose v2.20+ | Docker Desktop bản mới nhất |
| **Node.js** | Node.js v18+ & pnpm v9+ | Node.js v20 LTS |
| **Python** | Python 3.10+ | Python 3.12+ |

---

### 1.2. Các bước khởi chạy

#### Bước 1: Clone mã nguồn
```bash
git clone https://github.com/Viet-Hoang-2005/MLOps-paas-system.git
cd MLOps-paas-system
```

#### Bước 2: Thiết lập file biến môi trường `.env`
Sao chép template mẫu và điều chỉnh các biến cần thiết:
```bash
cp .env.example .env
```
Đảm bảo các cấu hình cốt lõi cho môi trường local:
```ini
EXECUTION_BACKEND=docker
REDIS_CONNECTION_MODE=direct
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/1
CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/3
CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@redis:6379/4
REDPANDA_BROKERS=redpanda:9092
DB_HOST_RW=postgres
DB_HOST_RO=postgres
DB_PORT=5432
DB_NAME=mlops_paas_db
DB_USER=postgres
DB_PASSWORD=postgres
```

#### Bước 3: Khởi động toàn bộ stack dịch vụ Backend
```bash
docker compose up --build -d
```
Kiểm tra trạng thái các container:
```bash
docker compose ps
```

Xem nhật ký hoạt động thời gian thực của Control Plane:
```bash
docker compose logs -f control-plane
```

#### Bước 4: Khởi chạy giao diện Web Dashboard (Frontend)
Mở một cửa sổ Terminal mới:
```bash
cd web
pnpm install --frozen-lockfile
pnpm dev
```
Giao diện sẽ sẵn sàng tại: `http://localhost:5173`.

---

### 1.3. Tùy chọn hạ tầng S3 AWS cho Local

Nếu bạn muốn môi trường Docker Compose cục bộ lưu trữ Model Artifacts thật trên AWS S3 thay vì mock local, bạn có thể tạo riêng một bucket S3 duy nhất thông qua cấu hình `s3-only.tfvars`:

```bash
cd infra/
terraform init
terraform apply -var-file="s3-only.tfvars"
```
Sau đó, lấy tên bucket được xuất ra (`s3_bucket_name`) và điền vào biến `AWS_BUCKET_NAME` trong file `.env` ở root.

---

### 1.4. Bảng tra cứu cổng và URL Local

| Dịch vụ | URL Local | Mục đích sử dụng |
|---|---|---|
| **React Dashboard** | `http://localhost:5173` | Giao diện điều khiển AI PaaS người dùng |
| **Control Plane API** | `http://localhost:8000/api/` | REST API Backend chính của Control Plane |
| **API Health Check** | `http://localhost:8000/health/ready` | Kiểm tra kết nối DB, Redis và tính sẵn sàng |
| **Model Server Gateway** | `http://localhost:5002/` | Cổng tiếp nhận suy luận tập trung |
| **ML Serving Worker** | `http://localhost:5001/health` | Phục vụ suy luận mô hình Scikit-Learn/XGBoost |
| **DL Serving Worker** | `http://localhost:5004/health` | Phục vụ suy luận mô hình BentoML Deep Learning |
| **MLflow Tracking UI** | `http://localhost:5003` | Theo dõi thí nghiệm và Model Registry |
| **Redpanda Console** | `http://localhost:8081` | Quản trị trực quan Kafka Topics & Consumer Groups |
| **pgAdmin 4 GUI** | `http://localhost:5050` | Giao diện quản trị PostgreSQL (admin@mlops.com / admin) |

---

## 2. Triển khai Môi trường Sản xuất (Production K3s trên AWS)

Quy trình triển khai trên môi trường sản xuất tuân thủ kiến trúc phân tách 3 lớp:
1. **Terraform:** Tạo hạ tầng IaaS (VPC, Subnets, EC2 Instances, ALB, IAM, S3, Secrets Manager, Route 53).
2. **AWS Secrets Manager & Scripts:** Đẩy biến môi trường an toàn lên đám mây.
3. **Ansible:** Chuẩn hóa Ubuntu OS, cài đặt cụm K3s (embedded etcd), và bàn giao cho **Argo CD**.
4. **Argo CD:** Tiếp quản toàn bộ việc triển khai các vi dịch vụ và toán tử theo **5 Sync Waves**.

```
+--------------------+        +---------------------+        +--------------------+
|  Terraform (IaaS)  | -----> |  Ansible (Bootstrap)| -----> |  Argo CD (GitOps)  |
+--------------------+        +---------------------+        +--------------------+
```

---

### 2.1. Yêu cầu chuẩn bị

- Máy điều khiển (Control Host) chạy Ubuntu 22.04 LTS hoặc WSL2 trên Windows.
- Đã cài đặt: `terraform >= 1.5`, `awscli v2`, `ansible >= 2.15`, `kubectl >= 1.28`.
- Khóa SSH Keypair trên AWS EC2 mang tên `mlops-keypair` trỏ tới file private key bí mật (ví dụ `~/.ssh/aws_key` với quyền `chmod 600`).
- Tên miền đã trỏ DNS về Cloudflare hoặc Route 53 (ví dụ `mlops-nids-nt114.id.vn`).

---

### 2.2. Bước 1: Khởi tạo hạ tầng AWS IaaS (Terraform)

Di chuyển vào thư mục hạ tầng:
```bash
cd infra/
terraform init
terraform fmt -check -recursive
terraform validate
```

#### Bước 1.1: Khởi tạo chứng chỉ SSL/TLS ACM
Tạo trước ACM Certificate để trích xuất CNAME DNS validation:
```bash
terraform apply -target='module.dns[0].aws_acm_certificate.mlops_cert'
terraform output -json acm_ssl_validation_records
```
Tạo các bản ghi CNAME được xuất ra trên trang quản lý DNS (Cloudflare/Route 53), đợi chứng chỉ chuyển sang trạng thái `ISSUED`.

#### Bước 1.2: Triển khai toàn bộ hạ tầng
```bash
terraform plan -out=tfplan
terraform apply tfplan
```
Lệnh này sẽ tự động khởi tạo:
- VPC với 2 Public Subnets và 2 Private Subnets.
- 1 EC2 Master Node (`t3.medium`) có Public IP làm Bastion SSH.
- 2 EC2 Worker Nodes (`t3.large`) nằm trong mạng Private Subnet.
- AWS Application Load Balancer (ALB) gắn chứng chỉ ACM SSL.
- S3 Buckets (`mlops-paas-artifacts` và `mlops-paas-runtime-logs`).
- 4 AWS Secrets Manager containers rỗng.
- IAM Instance Profiles và Karpenter SQS interruption queue.

---

### 2.3. Bước 2: Đồng bộ bí mật lên AWS Secrets Manager

Quay trở lại thư mục gốc của repository:
```bash
cd ..
```

Khởi tạo môi trường ảo Python và cài đặt thư viện cho script đẩy secret:
```bash
python3 -m venv .venv-secrets
source .venv-secrets/bin/activate
pip install -r scripts/requirements.txt
```

Chạy script tự động sinh và đồng bộ các nhóm bí mật:
```bash
# Đồng bộ toàn bộ các nhóm secret cấu hình sản xuất
python scripts/create_and_push_secrets_to_aws.py --groups 0 --yes
deactivate
```
Script sẽ nạp các thông tin mật (DB passwords, Harbor credentials, JWT RS256 Private/Public Keys, Webhook secrets) vào 3 container:
- `mlops/aws-secrets`
- `mlops/github-actions-secrets`
- `mlops/production-secrets`

---

### 2.4. Bước 3: Chuẩn bị máy chủ điều khiển Ansible (WSL / Linux)

Thiết lập môi trường Ansible:
```bash
python3 -m venv .venv-ansible
source .venv-ansible/bin/activate
pip install -r ansible/requirements.txt
ansible-galaxy collection install -r ansible/requirements.yml
```

Đảm bảo SSH key kết nối EC2 có quyền truy cập an toàn:
```bash
chmod 600 ~/.ssh/aws_key
```

Kiểm tra kết nối Dynamic Inventory từ Terraform:
```bash
cd ansible/
export ANSIBLE_CONFIG=./ansible.cfg
ansible-inventory -i inventory/terraform.py --graph
```

---

### 2.5. Bước 4: Bootstrap K3s và khởi động GitOps Core (Ansible)

Kiểm tra cú pháp playbook:
```bash
ansible-playbook -i inventory/terraform.py site.yml --syntax-check
```

Thực thi cài đặt theo từng phase có kiểm soát:

```bash
# 1. Chuẩn hóa OS và cài đặt cụm K3s (Master + Workers)
ansible-playbook -i inventory/terraform.py site.yml --tags bootstrap

# 2. Cài đặt Helm, Argo CD và khởi động Root Application (mlops-paas-system)
ansible-playbook -i inventory/terraform.py site.yml --tags platform-core

# 3. Kích hoạt môi trường huấn luyện đàn hồi Kubeflow & Karpenter (Tùy chọn)
ansible-playbook -i inventory/terraform.py site.yml --tags platform-training \
  -e deploy_training_platform=true \
  -e enable_karpenter=true
```

> [!NOTE]
> Ngay sau khi phase `platform-core` hoàn tất, **Argo CD** sẽ tự động đồng bộ toàn bộ tài nguyên từ repository Git theo đúng thứ tự 5 Sync Waves (`cluster` $\rightarrow$ `addons` $\rightarrow$ `platform` $\rightarrow$ `execution` $\rightarrow$ `workloads`). Bạn không cần chạy lệnh `kubectl apply` thủ công!

---

### 2.6. Bước 5: Xác minh trạng thái cụm K3s và Ingress Edge

Truy cập SSH vào Master Node thông qua ProxyJump:
```bash
ssh -i ~/.ssh/aws_key ubuntu@$(cd ../infra && terraform output -raw master_public_ip)
```

Kiểm tra trạng thái các node và ứng dụng GitOps:
```bash
# Kiểm tra nodes
sudo k3s kubectl get nodes -L workload-type

# Kiểm tra tình trạng đồng bộ Argo CD
sudo k3s kubectl get applications -n argocd \
  -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status

# Kiểm tra cơ sở dữ liệu CloudNativePG HA
sudo k3s kubectl get clusters.postgresql.cnpg.io -A

# Kiểm tra ExternalSecrets đồng bộ thành công từ AWS
sudo k3s kubectl get externalsecret -A
```

Kiểm tra trạng thái Target Group trên AWS ALB từ máy điều khiển:
```bash
aws elbv2 describe-target-health \
  --region ap-southeast-1 \
  --target-group-arn "$(cd ../infra && terraform output -raw alb_target_group_arn)" \
  --query 'TargetHealthDescriptions[*].[Target.Id,TargetHealth.State]' \
  --output table
```
Tất cả các targets phải hiển thị trạng thái `healthy`.

---

### 2.7. Bảng tra cứu Production Service URLs

| Dịch vụ | URL Production | Mô tả |
|---|---|---|
| **Frontend Web Dashboard** | `https://mlops-nids-nt114.id.vn` | Giao diện MLOps PaaS Dashboard |
| **Control Plane API** | `https://api.mlops-nids-nt114.id.vn/api/` | REST API của Control Plane |
| **Argo CD Dashboard** | `https://argocd.mlops-nids-nt114.id.vn` | Quản trị triển khai GitOps |
| **Argo Workflows UI** | `https://workflow.mlops-nids-nt114.id.vn` | Giám sát các pipeline huấn luyện/đóng gói |
| **Grafana Monitoring** | `https://grafana.mlops-nids-nt114.id.vn` | Dashboard quan sát tài nguyên và metrics |
| **MLflow Server** | `https://mlflow.mlops-nids-nt114.id.vn` | Experiment Tracking & Model Registry |
| **Harbor Registry** | `https://registry.mlops-nids-nt114.id.vn` | Private OCI Container Registry |

---

## 3. Gỡ cài đặt & Dọn dẹp Hạ tầng (Teardown & Cleanup)

> [!CAUTION]
> **Cảnh báo mất dữ liệu:** Thao tác này sẽ xóa vĩnh viễn dữ liệu trên cụm Kubernetes và toàn bộ tài nguyên đám mây AWS. Hãy sao lưu các artifact quan trọng trên S3 và cơ sở dữ liệu trước khi tiếp tục.

#### Bước 3.1: Dọn dẹp tài nguyên Kubernetes và Dynamic EBS Volumes
Truy cập vào Master Node để xóa Root Application và các PersistentVolumeClaims (để giải phóng các ổ cứng EBS do Kubernetes CSI tạo ra):
```bash
# Xóa root application để Argo CD prune các workloads
sudo k3s kubectl delete -f k8s/argocd/application.yaml --ignore-not-found

# Xóa toàn bộ PVCs để giải phóng volume EBS trên AWS
sudo k3s kubectl delete pvc --all -A
```

#### Bước 3.2: Tiêu hủy hạ tầng AWS qua Terraform
Thoát SSH về máy điều khiển:
```bash
cd infra/
terraform plan -destroy -out=destroy.tfplan
terraform apply destroy.tfplan
```
Terraform sẽ tự động dọn dẹp EC2 instances, VPC, ALB, Secrets Manager và các S3 buckets nhờ cấu hình `force_destroy = true`.
