# Đánh giá 7 đề xuất cải thiện hệ thống AI PaaS

Tài liệu này ghi lại trạng thái thực tế sau khi hệ thống được refactor theo hướng Control Plane Django, model-server gateway, dynamic ML/DL serving images, Argo Workflows, Harbor, Prometheus/Grafana, Kubeflow Training Operator và Karpenter.

Mục tiêu của bản cập nhật này không còn là kế hoạch ban đầu, mà là đối chiếu 7 đề xuất cải thiện với phần đã triển khai trong repo hiện tại, phần chỉ mới hoàn thành một phần, và phần còn lại nên để cho các giai đoạn sau.

---

## Checklist tổng quan

| # | Đề xuất | Trạng thái hiện tại | Ghi chú |
|---|---|---|---|
| 1 | Tối ưu cơ chế image/base image | Hoàn thành theo hướng khác | Giữ image riêng theo model, nhưng dùng base image để tái sử dụng layer; không dùng shared image + init container |
| 2 | Hỗ trợ ML + Deep Learning/BentoML | Hoàn thành | Tách gateway, machine-learning-serving và deep-learning-serving |
| 3 | Nối model thành pipeline giống n8n | Chưa làm | Nên để phase sau vì cần thiết kế executor và FE visual editor |
| 4 | Đánh giá suy giảm mô hình toàn diện | Hoàn thành một phần | Data drift đã có; prediction drift/ground truth feedback chưa hoàn thiện |
| 5 | Training bằng Kubeflow + Karpenter | Hoàn thành nền tảng | Đã chuyển khỏi AWS Batch/SageMaker sang Kubeflow PyTorchJob + Karpenter |
| 6 | Metrics/health phục vụ FE | Hoàn thành backend | FE sẽ thêm sau; backend đã có API query Prometheus |
| 7 | Billing theo tài nguyên sử dụng | Chưa làm | Phụ thuộc metrics, quota và pricing model |

---

## 1. Tối ưu cơ chế image/base image

**Trạng thái:** Hoàn thành theo hướng build image riêng dựa trên base image, không triển khai phương án shared base image + init container.

### Checklist

- [x] Chuẩn hóa build image động cho từng model/user.
- [x] Sử dụng base image cho ML serving và DL serving để Docker/Harbor tái sử dụng layer.
- [x] Giữ model artifact nằm trong image đã build để pod phục vụ model khởi động ổn định hơn.
- [x] Loại bỏ fallback deploy bằng shared base image + `MODEL_URI=s3://...`.
- [x] Loại bỏ S3 artifact downloader trong runtime serving.
- [ ] Bổ sung lifecycle cleanup/retention policy cho image cũ trên Harbor.

### Thực tế đã làm

Ban đầu có đề xuất dùng một shared base image duy nhất, sau đó để init container tải model từ S3 và chạy `pip install -r requirements.txt` khi pod khởi động. Sau khi đánh giá lại, hệ thống hiện chọn hướng thực tế hơn:

- Mỗi model sau khi upload/deploy vẫn được build thành image riêng.
- Image riêng này dựa trên base image của runtime tương ứng:
  - `machine-learning-serving` cho các flavor ML truyền thống.
  - `deep-learning-serving` cho các flavor Deep Learning như PyTorch/Keras thông qua BentoML.
- Model artifact và dependency của người dùng được đóng gói ở bước build bởi `model-packager`.
- Khi deploy, `deploy_adapter.py` yêu cầu image cụ thể đã được build thành công, thay vì cho phép fallback về shared image + `MODEL_URI`.

### Lý do không dùng init container cho artifact/dependency

Phương án init container giúp giảm số lượng image riêng, nhưng đổi lại có các vấn đề sau:

- Cold start lâu hơn vì mỗi lần pod restart phải tải model và cài dependency lại.
- Khó kiểm soát tính tái lập của môi trường phục vụ model.
- Rủi ro runtime cao hơn nếu network/S3/pip registry lỗi tại thời điểm pod khởi động.
- Dependency của người dùng có thể làm pod khởi động thất bại sau khi deployment đã được tạo.

Với hướng hiện tại, lỗi dependency/model artifact xảy ra sớm ở build stage. Pod deploy ra production nhận một image đã đóng gói hoàn chỉnh, dễ rollback và dễ quan sát hơn.

---

## 2. Hỗ trợ đa dạng mô hình AI với MLflow/FastAPI và BentoML

**Trạng thái:** Hoàn thành phần serving runtime chính.

### Checklist

- [x] Refactor `model-server` thành gateway trung tâm.
- [x] Tách runtime ML truyền thống sang `machine-learning-serving`.
- [x] Tách runtime Deep Learning sang `deep-learning-serving`.
- [x] Dùng BentoML cho Deep Learning serving.
- [x] Route public endpoint qua contract chung `/models/{version_uuid}/predict` và `/models/{version_uuid}/health`.
- [x] Build pipeline chọn runtime dựa trên flavor/model type hiện có.
- [x] Deploy workflow chỉ tạo worker Deployment/Service, không tạo ingress riêng cho từng model.
- [ ] Bật batching nâng cao cho DL khi payload/schema đã ổn định.

### Thực tế đã làm

Kiến trúc serving hiện tại được tách thành hai lớp:

1. **Gateway:** `services/model-server`
   - Xác thực API key/JWT.
   - Kiểm tra quyền truy cập public/private.
   - Resolve model record trong database/cache.
   - Route nội bộ tới worker service tương ứng.
   - Ghi production data sang Redpanda.
   - Expose metric gateway như request count, error rate và latency.

2. **Worker runtime:** mỗi model có Deployment/Service riêng.
   - ML truyền thống chạy qua `services/machine-learning-serving`.
   - Deep Learning chạy qua `services/deep-learning-serving`.
   - Worker chỉ tập trung load model và predict, không xử lý auth/multi-tenant routing.

Luồng request hiện tại:

```text
Client
  -> Traefik static ingress
  -> mlops-paas-model-server gateway
  -> endpoint-<tenant>-model-<hash>-svc
  -> ML/DL worker pod
```

### Điều chỉnh so với kế hoạch ban đầu

Ban đầu BentoML từng được bọc bằng FastAPI để ép cùng route contract. Sau refactor gateway, điều đó không còn cần thiết ở worker nữa. Contract public được giữ ở gateway, còn worker có thể dùng API native phù hợp với runtime.

Cách này có lợi hơn vì:

- Gateway là nơi duy nhất giữ public API contract.
- Worker ML/DL có thể thay đổi nội bộ mà không phá public endpoint.
- BentoML không cần bị ép vào một lớp FastAPI bên ngoài chỉ để giữ URL public.

---

## 3. Kết nối model thành pipeline giống n8n

**Trạng thái:** Chưa triển khai.

### Checklist

- [ ] Thiết kế model dữ liệu `Pipeline`, `PipelineNode`, `PipelineEdge`.
- [ ] Xây dựng pipeline executor cho inference.
- [ ] Hỗ trợ mapping output model A sang input model B.
- [ ] Thiết kế UI visual editor, ví dụ React Flow.
- [ ] Bổ sung quota/concurrency limit cho pipeline execution.

### Đánh giá hiện tại

Đề xuất này vẫn rất có giá trị, nhưng chưa nên gộp vào refactor serving hiện tại. Hệ thống vừa chuyển sang gateway + worker runtime động, nên cần ổn định các phần build/deploy/monitoring trước.

Kiến trúc hiện tại đã tạo nền tốt cho pipeline vì mọi model đều có contract public thống nhất qua gateway:

```text
/models/{version_uuid}/predict
/models/{version_uuid}/health
```

Khi làm pipeline sau này, executor có thể gọi gateway hoặc gọi service nội bộ tùy yêu cầu bảo mật/hiệu năng.

### Đề xuất phase sau

Phase đầu nên làm pipeline tuần tự đơn giản:

```text
Input -> Model A -> Transform -> Model B -> Output
```

Sau khi ổn định mới mở rộng sang DAG, branching, parallel execution và visual editor.

---

## 4. Đánh giá suy giảm mô hình toàn diện

**Trạng thái:** Hoàn thành một phần.

### Checklist

- [x] Log production data từ gateway sang Redpanda.
- [x] Có Evidently job để kiểm tra data drift.
- [x] Có Argo Workflow để chạy drift/evidently job.
- [ ] Bổ sung prediction drift chính thức.
- [ ] Log confidence/probability một cách chuẩn hóa cho mọi runtime.
- [ ] Thiết kế API nhận ground-truth feedback.
- [ ] Tính quality metrics như accuracy, precision, recall, F1 theo thời gian.

### Thực tế đã làm

Hệ thống hiện đã có nền tảng drift monitoring:

- Gateway nhận request predict.
- Gateway gửi production data gồm tenant, model, timestamp, features và prediction sang Redpanda.
- Consumer/control plane lưu dữ liệu production để phục vụ kiểm tra drift.
- Evidently job có thể so sánh reference data với production data.

Phần đã sẵn sàng nhất là **data drift**, vì không cần nhãn thực tế. Đây là loại monitoring phù hợp để chạy tự động sau khi đã tích lũy đủ production sample.

### Phần chưa hoàn thiện

Các loại suy giảm mô hình sâu hơn vẫn cần dữ liệu bổ sung:

| Loại monitoring | Trạng thái | Điều kiện cần |
|---|---|---|
| Data drift | Đã có nền tảng | Reference data + production features |
| Prediction drift | Chưa hoàn thiện | Chuẩn hóa lưu prediction distribution |
| Confidence drift | Chưa hoàn thiện | Runtime phải trả confidence/probability thống nhất |
| Model quality | Chưa làm | Cần ground truth/feedback từ người dùng |

Kết luận: hệ thống đã có nền monitoring dữ liệu, nhưng chưa phải full model performance monitoring.

---

## 5. Training bằng Kubeflow + Karpenter

**Trạng thái:** Hoàn thành nền tảng training mới.

### Checklist

- [x] Chuyển định hướng training từ AWS Batch/SageMaker sang Kubeflow + Karpenter.
- [x] Thêm `services/training-runner` vào CI/CD image build/push.
- [x] Workflow training dùng image registry đầy đủ thay vì local tag.
- [x] `training-workflowtemplate.yaml` chạy `python /app/train_runner.py`.
- [x] Truyền các env quan trọng: S3 source, training data, output, training job id, model version.
- [x] Tạo namespace `user-jobs` và cấu hình quyền cơ bản cho training job.
- [x] Tách Karpenter CPU NodePool và GPU NodePool.
- [x] GPU jobs có toleration và `resources.limits.nvidia.com/gpu`.
- [x] Bổ sung script cài Kubeflow Training Operator và Karpenter controller.
- [x] Bổ sung bootstrap K3s agent cho node do Karpenter tạo.
- [ ] Mở rộng workflow cho TFJob/XGBoostJob/MPIJob.
- [ ] Thêm tenant quota và max concurrent training jobs.

### Thực tế đã làm

Hệ thống training hiện đã đi theo hướng Kubernetes-native:

- Control Plane tạo training request.
- Argo Workflows submit Kubeflow `PyTorchJob`.
- Kubeflow Training Operator tạo training pod.
- Nếu cụm thiếu capacity, Karpenter provision EC2 node mới.
- Node mới join vào K3s bằng bootstrap userData/token.
- Training runner tải source/data từ S3, chạy training, ghi output/model artifacts và tracking metadata.

Luồng tổng quát:

```text
User
  -> Control Plane
  -> Argo Workflow
  -> Kubeflow PyTorchJob
  -> Training Runner Pod
  -> S3/MLflow artifacts
```

### Phần cần làm tiếp

Nền tảng hiện chủ yếu ổn cho PyTorch-style training. Nếu muốn hỗ trợ đa framework đầy đủ, cần thêm:

- `TFJob` cho TensorFlow.
- `XGBoostJob` cho XGBoost distributed training.
- `MPIJob` cho Horovod/MPI.
- Cơ chế quota để tránh một tenant tạo quá nhiều job song song làm tăng chi phí EC2.

---

## 6. Metrics/health phục vụ giao diện Web

**Trạng thái:** Hoàn thành backend, FE sẽ thêm sau.

### Checklist

- [x] Prometheus/Grafana đã có trong cụm.
- [x] ServiceMonitor scrape dynamic model worker services.
- [x] ServiceMonitor scrape thêm model-server gateway.
- [x] Gateway expose metric request/error/latency theo `tenant_id`, `project_id` và `model_version_id`.
- [x] Control Plane có API observability cho từng model.
- [x] API trả 3 nhóm dữ liệu: traffic, resource, health.
- [x] Alert rule dùng gateway metric `paas_*` cho inference latency/error.
- [ ] FE hiển thị dashboard metrics trong trang model detail/management.
- [ ] Bổ sung query range/time-series cho chart lịch sử dài hơn.
- [ ] Bổ sung GPU metrics khi cụm có DCGM exporter.

### Thực tế đã làm

Backend monitoring hiện được chia rõ nguồn dữ liệu:

| Nhóm | Nguồn metric | Ý nghĩa |
|---|---|---|
| Traffic/latency/error | `model-server` gateway | Đo đường public end-to-end từ client tới worker và quay lại |
| CPU/RAM/network | worker pod | Đo tài nguyên thực tế của pod phục vụ model |
| Replica/uptime/health | kube-state/cAdvisor + trạng thái DB | Đo lifecycle của deployment model |

Gateway metric chính:

```text
paas_predictions_total{tenant_id, project_id, model_version_id, status}
paas_prediction_latency_seconds_bucket{tenant_id, project_id, model_version_id}
```

Control Plane API hiện có thể trả về:

```text
group1_traffic
group2_resources
group3_health
```

Điểm quan trọng là FE sau này không cần query Prometheus trực tiếp. FE chỉ gọi Control Plane, còn Control Plane chịu trách nhiệm filter theo tenant/model để giữ multi-tenant isolation.

---

## 7. Billing theo tài nguyên sử dụng

**Trạng thái:** Chưa triển khai.

### Checklist

- [ ] Thiết kế bảng `UsageRecord`.
- [ ] Thiết kế bảng `PricingPlan`.
- [ ] Tạo collector định kỳ query Prometheus.
- [ ] Tính vCPU-hour, GB-RAM-hour, GPU-hour.
- [ ] Tính request count và network egress.
- [ ] Tính storage usage từ S3/Harbor.
- [ ] Tạo invoice/estimated cost theo tenant.
- [ ] Bổ sung audit trail và idempotency cho collector.

### Đánh giá hiện tại

Billing chưa nên làm ngay cho tới khi metrics backend và quota ổn định. Tuy vậy, các thay đổi monitoring vừa triển khai đã tạo nền cần thiết cho billing:

- Request count có thể lấy từ `paas_predictions_total`.
- Latency/error có thể dùng để đánh giá SLA.
- CPU/RAM/network có thể lấy theo worker pod.
- Training usage có thể tính từ Kubeflow job duration và Karpenter node type.

### Đề xuất khi triển khai

Nên bắt đầu bằng **estimated cost**, chưa thu tiền thật:

```text
Prometheus
  -> Usage Collector định kỳ
  -> UsageRecord trong PostgreSQL
  -> Estimated cost trên dashboard
```

Sau khi dữ liệu usage ổn định, mới tích hợp invoice/payment provider.

---

## Kết luận cập nhật

So với kế hoạch ban đầu, hệ thống đã hoàn thành các phần nền tảng quan trọng nhất:

- Serving runtime đã tách rõ gateway, ML worker và DL/BentoML worker.
- Build/deploy image động đã hỗ trợ cả ML và DL.
- Public endpoint đã thống nhất qua gateway.
- Training đã chuyển sang Kubeflow + Karpenter.
- Monitoring backend đã sẵn sàng cho FE tích hợp.

Các phần nên ưu tiên tiếp theo:

1. Hoàn thiện FE dashboard cho observability API hiện có.
2. Bổ sung retention/cleanup policy cho Harbor image theo tenant/model version.
3. Chuẩn hóa prediction/confidence schema để mở rộng prediction drift và confidence monitoring.
4. Thiết kế quota cho training và serving trước khi làm billing.
5. Để pipeline editor/n8n-style sang phase sau vì đây là tính năng lớn, cần thiết kế riêng cả backend executor và frontend editor.
