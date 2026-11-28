# Báo cáo rà soát & tối ưu Kubernetes (`workloads/`, `platform/`, `cluster/`, `gitops/production/`)

> Tài liệu tổng hợp kết quả rà soát toàn bộ manifest YAML thuộc `k8s/workloads/`, `k8s/platform/`, `k8s/cluster/`, và `k8s/gitops/production/`, đối chiếu chéo với code dịch vụ trong `services/` và CI checks trong `k8s/verify/`.

---

## Phần 1: Lỗi nghiêm trọng & Bug runtime (P0/P1)

### 1.1. Cluster (`k8s/cluster/`)
1. **Sai `deviceName: /dev/xvda` cho Ubuntu 22.04 AMI trong Karpenter `EC2NodeClass`**
   - [`nodeclasses.yaml#L29-L34,L108-L113`](file:///d:/AI%20Models/mlops-paas-system/k8s/cluster/capacity/karpenter/nodeclasses.yaml#L29-L34): Cả `training-cpu` và `training-gpu` đều chọn AMI Ubuntu 22.04 (`ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*`, owner `099720109477`), có `RootDeviceName` là `/dev/sda1`, không phải `/dev/xvda`. Khai báo `/dev/xvda` gây lỗi `InvalidBlockDeviceMapping` hoặc giữ `/` ở 8 GiB mặc định trong khi gắn thêm một volume 100 GiB chưa format/mount — dễ làm cạn ổ cho containerd, 12.5 GiB `emptyDir` training, và driver GPU Operator.
2. **Trùng 2 default `StorageClass` (`ebs-gp3` vs `local-path`)**
   - [`ebs-gp3-storageclass.yaml#L6`](file:///d:/AI%20Models/mlops-paas-system/k8s/cluster/storage/ebs-gp3-storageclass.yaml#L6): `ebs-gp3` đặt `is-default-class: "true"`, trong khi K3s mặc định vẫn giữ `local-path` là default. Các PVC không chỉ định `storageClassName` (như `workspace` 10Gi trong [`build/workflow.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/build/workflow.yaml#L45-L52) và `redpanda-data` 5Gi trong [`redpanda/statefulset.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/platform/redpanda/statefulset.yaml#L72-L79)) sẽ bind không xác định.
3. **`reclaimPolicy: Delete` trên `ebs-gp3` dùng cho Stateful Databases**
   - [`ebs-gp3-storageclass.yaml#L22`](file:///d:/AI%20Models/mlops-paas-system/k8s/cluster/storage/ebs-gp3-storageclass.yaml#L22): Postgres, Redis và Loki đều dùng `ebs-gp3` (`reclaimPolicy: Delete`). Xóa nhầm PVC hoặc ArgoCD prune sẽ xóa vĩnh viễn EBS volume. Cần tách `ebs-gp3-retain` (`reclaimPolicy: Retain`) riêng cho stateful stores.

### 1.2. GitOps (`k8s/gitops/production/`)
4. **Deadlock sync-wave khi bootstrap Alertmanager `ExternalSecret`**
   - [`monitoring-alertmanager-secret.yaml#L7`](file:///d:/AI%20Models/mlops-paas-system/k8s/gitops/production/applications/addons/monitoring-alertmanager-secret.yaml#L7) đặt `sync-wave: "-41"` trực tiếp trong root App-of-Apps, nhưng `ExternalSecret` CRD chỉ được cài ở wave `-40` ([`external-secrets.yaml#L7`](file:///d:/AI%20Models/mlops-paas-system/k8s/gitops/production/applications/addons/external-secrets.yaml#L7)) và `ClusterSecretStore/aws-secrets-manager` tạo ở wave `-30` ([`secret-store.yaml#L7`](file:///d:/AI%20Models/mlops-paas-system/k8s/gitops/production/applications/cluster/secret-store.yaml#L7)). Trên cluster mới, wave `-41` sẽ lỗi vì chưa có CRD và chặn toàn bộ wave sau.
5. **Trùng key YAML trong `gpu-operator.yaml`**
   - [`gpu-operator.yaml#L64-L67`](file:///d:/AI%20Models/mlops-paas-system/k8s/gitops/production/applications/addons/gpu-operator.yaml#L64-L67): `interval: 30s` và `honorLabels: true` bị lặp 2 lần liên tiếp dưới `dcgmExporter.serviceMonitor`.
6. **Thiếu OCI repository Secret cho `ghcr.io/kubeflow/charts`**
   - [`kubeflow-trainer.yaml#L24-L26`](file:///d:/AI%20Models/mlops-paas-system/k8s/gitops/production/applications/addons/kubeflow-trainer.yaml#L24-L26) kéo OCI chart từ `ghcr.io/kubeflow/charts`, nhưng [`repositories/addons.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/gitops/production/repositories/addons.yaml) chưa khai báo repository Secret `enableOCI: "true"` cho repo này.
7. **Thiếu `ignoreDifferences` cho `ExternalSecret` trên Redis và root App**
   - [`redis.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/gitops/production/applications/platform/redis.yaml) (và root [`application.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/argocd/application.yaml) quản lý `monitoring-alertmanager-secret.yaml`) thiếu `ignoreDifferences` cho `/metadata/annotations/force-sync`, dễ gây vòng lặp OutOfSync/selfHeal khi ESO force-sync.

### 1.3. Workloads (`k8s/workloads/`)
8. **Alert `CeleryHighTaskFailureRate` chết hoàn toàn (sai tên metric)**
   - [`control-plane/prometheus-rule.yaml#L68-L70`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/base/control-plane/prometheus-rule.yaml#L68-L70) query `control_plane_celery_tasks_total{status="failure"}`, nhưng metric này chỉ tăng trong worker Celery (không được scrape). Endpoint `/health/metrics` của control-plane thực tế xuất **`control_plane_celery_shared_tasks_total`** ([`metrics.py#L70-L74`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/common/metrics.py#L70-L74)).
9. **Control-plane `sh -c` thiếu `exec` (mất graceful shutdown) & thiếu `PROMETHEUS_MULTIPROC_DIR`**
   - [`control-plane/deployment.yaml#L117-L119`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/base/control-plane/deployment.yaml#L117-L119): `sh` làm PID 1 không forward `SIGTERM` tới `gunicorn`, khiến pod treo 30s rồi bị `SIGKILL` mỗi lần rollout. Đồng thời `--workers 3` gọi `generate_latest()` không có `PROMETHEUS_MULTIPROC_DIR`, làm metric Prometheus reset ngẫu nhiên theo worker được scrape.
10. **Consumer tạo topic 1 partition → vô hiệu hóa KEDA scale 1..5**
    - [`consumer/deployment.yaml#L63`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/base/consumer/deployment.yaml#L63): `rpk topic create` thiếu `-p/--partitions`, Redpanda mặc định tạo 1 partition nên replica 2–5 do [`consumer/scaledobject.yaml#L16-L17`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/base/consumer/scaledobject.yaml#L16-L17) scale ra luôn rảnh.
11. **Thiếu `readinessProbe` / `livenessProbe` trên nhiều deployment quan trọng**
    - Thiếu trên [`web/deployment.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/base/web/deployment.yaml#L36-L57), [`consumer/deployment.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/base/consumer/deployment.yaml#L75-L110), [`celery-deployment.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/base/control-plane/celery-deployment.yaml), [`redpanda/statefulset.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/platform/redpanda/statefulset.yaml#L39-L71), và [`cloudflare/deployment.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/platform/cloudflare/deployment.yaml#L47-L70) (cũng thiếu `--metrics 0.0.0.0:2000`).
12. **Hardcode `namespace: mlops-paas-core` trong `base/` PDB**
    - [`control-plane/pdb.yaml#L5,L24`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/base/control-plane/pdb.yaml#L5) và [`model-server/pdb.yaml#L5`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/base/model-server/pdb.yaml#L5) hardcode namespace trong `base/` thay vì để overlay quyết định.

### 1.4. Platform (`k8s/platform/`)
13. **Harbor `nodeSelector` đặt sai cấp + lưu dữ liệu trên `local-path`**
    - [`harbor/values.yaml#L13-L25,L94-L150`](file:///d:/AI%20Models/mlops-paas-system/k8s/platform/harbor/values.yaml#L13-L25): `database.nodeSelector`, `redis.nodeSelector`, `metrics.nodeSelector` không đúng schema Harbor chart 1.19.4 (phải là `database.internal.nodeSelector` và `redis.internal.nodeSelector`). Ngoài ra toàn bộ PVC Harbor dùng `local-path` — mất node worker là mất toàn bộ database/metadata của Harbor.
14. **Redis & Postgres `PrometheusRule` báo sai**
    - [`redis/prometheus-rule.yaml#L45-L54`](file:///d:/AI%20Models/mlops-paas-system/k8s/platform/redis/prometheus-rule.yaml#L45-L54): `RedisHAPVCAlmostFull` không lọc `persistentvolumeclaim` nên quét nhầm cả PVC Postgres và Redpanda; `RedisHAMemoryHigh` không loại trừ `redis-cache` (đang chạy `allkeys-lru` nên đầy RAM là bình thường).
    - [`postgres/prometheus-rule.yaml#L31`](file:///d:/AI%20Models/mlops-paas-system/k8s/platform/postgres/prometheus-rule.yaml#L31): `PostgresHighConnections` cộng tổng connection của cả 2 instance (`sum(...) > 80`) thay vì tính tỷ lệ trên `max_connections: 200` của từng pod.
15. **Postgres cấu hình RAM dễ OOM dưới limit `1Gi` + tag `:17` trôi + chưa có backup**
    - [`postgres/cluster.yaml#L32-L72`](file:///d:/AI%20Models/mlops-paas-system/k8s/platform/postgres/cluster.yaml#L32-L72): `shared_buffers: 256MB`, `maintenance_work_mem: 256MB`, `work_mem: 32MB`, `max_connections: 200` dễ vượt `limits.memory: 1Gi` khi chạy autovacuum/sort đồng thời; `postgresql:17` chưa pin minor version; thiếu `spec.backup`/WAL archiving lên S3.
16. **Redpanda hardcode `redpanda-0` trong `--advertise-kafka-addr` và thiếu `storageClassName`**
    - [`redpanda/statefulset.yaml#L53-L54,L72-L79`](file:///d:/AI%20Models/mlops-paas-system/k8s/platform/redpanda/statefulset.yaml#L53-L54): Không thể scale `replicas > 1` nếu hardcode `redpanda-0`.

---

## Phần 2: Lỗ hổng bảo mật (Security)

1. **`ClusterSecretStore` chưa giới hạn namespace (`spec.conditions`)**
   - [`cluster-secret-store.yaml#L14-L20`](file:///d:/AI%20Models/mlops-paas-system/k8s/cluster/secret-store/cluster-secret-store.yaml#L14-L20): Không có `spec.conditions`. Kết hợp với IAM `resources = ["*"]`, mọi namespace (kể cả `mlops-paas-training`, `mlops-paas-serving`) đều có thể tạo `ExternalSecret` đọc toàn bộ secret trong AWS Secrets Manager.
2. **`NetworkPolicy` quá rộng hoặc còn thiếu**
   - [`redis/network-policy.yaml#L25-L39`](file:///d:/AI%20Models/mlops-paas-system/k8s/platform/redis/network-policy.yaml#L25-L39): Cho phép `mlops-paas-serving` (pod untrusted của user không hề dùng Redis) và toàn bộ `mlops-paas-data` / `mlops-paas-core` truy cập Redis/Sentinel.
   - [`redpanda/network-policy.yaml#L26-L47`](file:///d:/AI%20Models/mlops-paas-system/k8s/platform/redpanda/network-policy.yaml#L26-L47): Cho phép toàn bộ `mlops-paas-execution` truy cập Kafka `9092` (thực tế không có workflow nào trong `k8s/argo/` kết nối Redpanda) và mở Admin API `9644` (không auth) cho toàn bộ `monitoring`.
   - [`postgres/network-policy.yaml#L30-L39`](file:///d:/AI%20Models/mlops-paas-system/k8s/platform/postgres/network-policy.yaml#L30-L39): Mở port `5432` cho toàn bộ `mlops-paas-execution` (chỉ `mlops-paas-evidently` cần) và toàn bộ `mlops-paas-core`; Postgres còn bật `enableSuperuserAccess: true` và `owner: postgres` ([`postgres/cluster.yaml#L31,L38`](file:///d:/AI%20Models/mlops-paas-system/k8s/platform/postgres/cluster.yaml#L31)).
   - [`control-plane/network-policy.yaml#L36-L49`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/base/control-plane/network-policy.yaml#L36-L49): Thiếu `podSelector` khi nhận traffic từ `mlops-paas-execution`, `mlops-paas-training`, `monitoring`.
   - Chưa có NetworkPolicy cho `harbor`, `cloudflare`, `celery-beat`, `celery-health-worker`; toàn bộ `workloads/` và `platform/` chưa có `Egress` NetworkPolicy.
3. **Hardening container, namespace & ingress công khai**
   - [`web/deployment.yaml#L30-L46`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/base/web/deployment.yaml#L30-L46) chạy quyền `root` với `NET_BIND_SERVICE`, `CHOWN`, `SETGID`, `SETUID`; toàn bộ container trong `workloads/` và `cloudflare`/`redpanda`/`redis` thiếu `readOnlyRootFilesystem: true` / `seccompProfile`.
   - `collect-static` initContainer ([`control-plane/deployment.yaml#L59-L94`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/base/control-plane/deployment.yaml#L59-L94)) nhận thừa nhiều secret (`JWT_PRIVATE_KEY`, `CONTROL_PLANE_WEBHOOK_SECRET`, `ARGO_EVENTS_WEBHOOK_TOKEN`, Redis passwords).
   - [`namespaces.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/cluster/namespaces/namespaces.yaml): 21 namespace chưa gắn Pod Security Standards (`pod-security.kubernetes.io/enforce`), chưa có `ResourceQuota` / `LimitRange`.
   - [`nodeclasses.yaml#L31-L64`](file:///d:/AI%20Models/mlops-paas-system/k8s/cluster/capacity/karpenter/nodeclasses.yaml#L31-L64): Thiếu `encrypted: true` trên EBS volume và `userData` chạy `curl https://get.k3s.io | sh` không kiểm tra checksum.
   - [`routing/ingress.yaml#L35,L85`](file:///d:/AI%20Models/mlops-paas-system/k8s/platform/routing/ingress.yaml#L35): Expose `/admin` trực tiếp qua ALB không có rate-limit/allowlist middleware, và `traefik-ping-expose` khớp `/ping` không giới hạn `Host(...)`.
   - [`verify-platform-images.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/cluster/image/verify-platform-images.yaml) dùng `failurePolicy: Fail` trên mọi namespace không có `exclude` trong khi Kyverno chạy 1 replica, và [`cluster/image/external-secrets.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/cluster/image/external-secrets.yaml) dùng chung credential push Harbor thay vì robot read-only.

---

## Phần 3: Cấu hình dư thừa & lệch luồng (Legacy / Mismatch)

| Nhóm | Vị trí | Tình trạng thực tế |
| --- | --- | --- |
| **ConfigMap keys chết** | [`consumer/configmap.yaml#L30`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/base/consumer/configmap.yaml#L30), [`control-plane/configmap.yaml#L24,L55,L57,L66`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/base/control-plane/configmap.yaml#L24) | `GITHUB_REPO`, `CONTROL_PLANE_DB_SCHEMA`, `KAFKA_TOPIC`, `JWKS_URL`, `MLFLOW_TRACKING_REQUIRED` không còn được code Python đọc. |
| **`REDIS_SENTINEL_PASSWORD` dư ở `model-server`** | [`model-server/deployment.yaml#L79-L83`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/base/model-server/deployment.yaml#L79-L83), [`overlays/production/model-server/external-secrets.yaml#L26`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/overlays/production/model-server/external-secrets.yaml#L26) | `model-server` đang chạy `REDIS_CONNECTION_MODE: "direct"`, không dùng Sentinel. |
| **`hosts` dư trong `celery-scaledobject.yaml`** | [`celery-scaledobject.yaml#L44-L45`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/base/control-plane/celery-scaledobject.yaml#L44-L45) | Khai báo trùng `hosts` (kèm `:26379`) và `addresses` với cùng một chuỗi. |
| **Listener Kafka cũ `19092`** | [`redpanda/statefulset.yaml#L52-L59`](file:///d:/AI%20Models/mlops-paas-system/k8s/platform/redpanda/statefulset.yaml#L52-L59), `service.yaml`, `network-policy.yaml` | `OUTSIDE://localhost:19092` từ Docker Compose cũ không thể truy cập từ pod khác và không workload nào dùng. |
| **Key dư/trùng ở Harbor & Postgres** | [`harbor/values.yaml#L103-L127`](file:///d:/AI%20Models/mlops-paas-system/k8s/platform/harbor/values.yaml#L103-L127), [`postgres/external-secrets.yaml#L22-L23`](file:///d:/AI%20Models/mlops-paas-system/k8s/platform/postgres/external-secrets.yaml#L22-L23) | `database.resources`/`redis.resources` bị bỏ qua; `DB_USER`/`DB_PASSWORD` trong `postgresql-bootstrap-secret` không được CNPG hay workload nào dùng. |
| **Monitor khai báo sai `namespace`** | [`postgres/pod-monitor.yaml#L7`](file:///d:/AI%20Models/mlops-paas-system/k8s/platform/postgres/pod-monitor.yaml#L7), [`redpanda/servicemonitor.yaml#L7`](file:///d:/AI%20Models/mlops-paas-system/k8s/platform/redpanda/servicemonitor.yaml#L7) | Ghi `namespace: monitoring` nhưng `kustomization.yaml` ghi đè thành `mlops-paas-data`. |
| **Rule `orphanedResources.ignore` cũ & namespace legacy** | [`projects/workloads.yaml#L44-L48`](file:///d:/AI%20Models/mlops-paas-system/k8s/gitops/production/projects/workloads.yaml#L44-L48), [`projects/platform.yaml#L39-L44`](file:///d:/AI%20Models/mlops-paas-system/k8s/gitops/production/projects/platform.yaml#L39-L44), [`projects/execution.yaml#L48-L55`](file:///d:/AI%20Models/mlops-paas-system/k8s/gitops/production/projects/execution.yaml#L48-L55), [`projects/cluster.yaml#L15`](file:///d:/AI%20Models/mlops-paas-system/k8s/gitops/production/projects/cluster.yaml#L15) | Ignore `cnpg-default-monitoring` nhầm project; ignore `argo-workflows-workflow` dù `workflow.rbac.create: false`; vẫn dùng destination namespace `mlops-paas-system` cho cluster apps. |
| **Label không đồng nhất & `syncPolicy` bị đè** | [`overlays/production/control-plane/external-secrets.yaml#L11`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/overlays/production/control-plane/external-secrets.yaml#L11), [`kubeflow-trainer.yaml#L68-L71`](file:///d:/AI%20Models/mlops-paas-system/k8s/gitops/production/applications/addons/kubeflow-trainer.yaml#L68-L71) | ExternalSecret dùng `component: api` thay vì `backend`; `syncPolicy` trong `kubeflow-trainer.yaml` bị patch của `applications/kustomization.yaml` ghi đè. |

---

## Phần 5: Lộ trình đề xuất xử lý

### Đợt 1 — Vá lỗi P0/P1 & Bug vận hành (Ưu tiên cao nhất)
- [x] Sửa `deviceName: /dev/sda1` và `encrypted: true` trên 2 `EC2NodeClass` trong `k8s/cluster/capacity/karpenter/nodeclasses.yaml`.
- [x] Đặt `reclaimPolicy: Retain` trực tiếp cho `ebs-gp3` (`ebs-gp3-storageclass.yaml`) để bảo vệ stateful DBs (Postgres, Redis replication, Redpanda, Harbor, Loki), dùng `local-path` cho dữ liệu tạm (`build` workspace, `redis-cache`), và bỏ `is-default-class` trên `ebs-gp3` để tránh xung đột 2 default StorageClass.
- [x] Xử lý bootstrap deadlock `monitoring-alertmanager-secret.yaml` (đưa vào wave sau `-30` hoặc chuyển sang application/platform thích hợp), xóa key lặp trong `gpu-operator.yaml`, thêm OCI repo Secret cho `ghcr.io/kubeflow/charts`, và bổ sung `ignoreDifferences` cho `ExternalSecret` ở `redis.yaml`.
- [x] Sửa `control-plane/deployment.yaml` (`exec gunicorn` + `PROMETHEUS_MULTIPROC_DIR`), sửa alert `CeleryHighTaskFailureRate` sang `control_plane_celery_shared_tasks_total`, thêm `-p 6` (hoặc `>= 5`) cho `init-kafka-topic` ở `consumer/deployment.yaml`, và bổ sung probes cho `web`, `consumer`, `celery-*`, `redpanda`, `cloudflared`.
- [x] Sửa `harbor/values.yaml` (`database.internal.nodeSelector`, `redis.internal.nodeSelector`, bỏ `metrics.nodeSelector`, chuyển PVC sang `ebs-gp3`), sửa `redis/prometheus-rule.yaml`, `postgres/prometheus-rule.yaml`, và điều chỉnh memory tuning / pin minor tag / `spec.backup` cho `postgres/cluster.yaml`.

### Đợt 2 — Siết chặt bảo mật
- [x] Giới hạn `spec.conditions` trên `ClusterSecretStore/aws-secrets-manager` chỉ cho phép các namespace sở hữu `ExternalSecret`.
- [x] Thu hẹp `NetworkPolicy` của `redis` (chặn `mlops-paas-serving`), `redpanda` (chặn `mlops-paas-execution`, thu hẹp `9644` chỉ cho Prometheus), `postgres` (chỉ mở cho `mlops-paas-evidently` trong `mlops-paas-execution` và `control-plane`/`consumer` trong `mlops-paas-core`), và bổ sung NetworkPolicy cho `harbor`, `cloudflare`, `celery-beat`, `celery-health-worker`.
- [x] Chạy `web` non-root, bổ sung `securityContext` (`readOnlyRootFilesystem`, `seccompProfile`, `drop: [ALL]`), gắn Pod Security Standards + `ResourceQuota` cho `namespaces.yaml`, và bảo vệ `/admin` + `/ping` trong `routing/ingress.yaml`.

### Đợt 3 — Dọn dẹp cấu hình thừa & tối ưu
- [x] Gỡ các ConfigMap keys chết (`GITHUB_REPO`, `CONTROL_PLANE_DB_SCHEMA`, `KAFKA_TOPIC`, `JWKS_URL`, `MLFLOW_TRACKING_REQUIRED`), `REDIS_SENTINEL_PASSWORD` ở `model-server`, listener `19092` ở `redpanda`, `hosts` trùng ở `celery-scaledobject.yaml`, và rule `orphanedResources.ignore` cũ trong `gitops/production/projects/`.