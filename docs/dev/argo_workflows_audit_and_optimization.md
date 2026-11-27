# Báo Cáo Rà Soát & Đề Xuất Tối Ưu `k8s/argo/` (Argo Events, Workflows & Runtimes)

Báo cáo tổng hợp kết quả rà soát toàn bộ 38 file trong [`k8s/argo/`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo) (`events/`, `workflows/`, `runtimes/`, `job_ops.py`) đối chiếu chéo với [`services/control-plane/`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane), `model-packager`, `training-runner`, `evidently`, `machine-learning-serving`, và `deep-learning-serving`.

---

## Phần 1: Các bug tiềm ẩn cần xử lý (phân loại theo mức độ)

> [!CAUTION]
> Các mục **P0 (Nghiêm trọng)** dưới đây có thể gây lỗi trực tiếp trên production K3s (lỗi load model, chậm rút pod lỗi khỏi Service, hoặc tràn đĩa khi build DL image).

### P0 — Nghiêm trọng (Cần xử lý ngay)

1. **[x] `MODEL_URI` trên Argo Deployment truyền nhầm `s3://...` thay vì `/app/model_artifact`, và thiếu `TENANT_ID`** *(Đã sửa)*
   - [`argo_backends.py#L302`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/infrastructure/execution/argo_backends.py#L302) trước đây truyền `model_uri` là `s3://...`, trong khi [`docker_backends.py#L248-L249`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/infrastructure/execution/docker_backends.py#L248-L249) truyền `MODEL_URI="/app/model_artifact"` (vì model đã đóng gói sẵn trong image) và `TENANT_ID`. Theo kiến trúc hiện tại, chỉ `control-plane` được dùng `boto3` thao tác S3 (các service khác chỉ nhận Presigned S3 hoặc dùng artifact đóng gói sẵn; IMDS trên pod cũng bị chặn bởi NetworkPolicy).
   - **Đã khắc phục:** `ArgoDeploymentBackend.deploy` đã sửa truyền `"model_uri": "/app/model_artifact"` và [`deploy/workflow.yaml#L138`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/deploy/workflow.yaml#L138) đã bổ sung `TENANT_ID` cho container `model-server`.

2. **[x] `readinessProbe` đặt `failureThreshold: 150` (25 phút) → pod chết không được rút khỏi Service** *(Đã sửa)*
   - [`deploy/workflow.yaml#L158-L166`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/deploy/workflow.yaml#L158-L166) trước đây sao chép `failureThreshold: 150` của `startupProbe` sang `readinessProbe`.
   - **Đã khắc phục:** Đã hạ `readinessProbe.failureThreshold` xuống `3` (tối đa ~30 giây trước khi rút pod khỏi Service endpoints, vẫn giữ `startupProbe.failureThreshold: 150` cho model khởi động chậm) và bổ sung kiểm tra vào [`validate_execution.py`](file:///d:/AI%20Models/mlops-paas-system/k8s/verify/validate/validate_execution.py).

3. **[x] PVC `workspace` của Build chỉ có `2Gi` + Kaniko `:latest` xuất `/workspace/image.tar` → dễ tràn đĩa với DL/PyTorch/TF** *(Đã sửa phần Build PVC & Kaniko)*
   - [`build/workflow.yaml#L39-L46,L197`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/build/workflow.yaml#L39-L46) đã nâng PVC `workspace` từ `2Gi` lên `10Gi`, thêm `volumeClaimGC: {strategy: OnWorkflowCompletion}` để thu hồi PVC ngay khi workflow xong, và pin Kaniko sang `gcr.io/kaniko-project/executor:v1.23.2` (cùng kiểm tra ở [`validate_execution.py`](file:///d:/AI%20Models/mlops-paas-system/k8s/verify/validate/validate_execution.py)).
   - **Đã khắc phục:** Pod serving ở [`deploy/workflow.yaml#L148`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/deploy/workflow.yaml#L148) đã tách `limits.memory` thành `2Gi` cho `model_type == 'dl'` và `1Gi` cho `ml`.

### P1 — Rò rỉ tài nguyên, bảo mật & độ tin cậy callback

4. **[x] Rò rỉ Workflow / Completed Pod / PVC trên `mlops-paas-execution` do thiếu `ttlStrategy`, `podGC` & `volumeClaimGC`** *(Đã sửa)*
   - Đã bổ sung `ttlStrategy: {secondsAfterCompletion: 3600}` và `podGC: {strategy: OnPodCompletion}` cho cả 4 `WorkflowTemplate` chính ([`build/workflow.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/build/workflow.yaml), [`deploy/workflow.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/deploy/workflow.yaml), [`evidently/workflow.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/evidently/workflow.yaml), [`training/workflow.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/training/workflow.yaml)), kèm `volumeClaimGC: {strategy: OnWorkflowCompletion}` cho `build/workflow.yaml`.
   - Đã bổ sung `ttlStrategy: {secondsAfterCompletion: 300}` và `podGC: {strategy: OnPodCompletion}` cho `build-workflow-trigger` và `deploy-workflow-trigger` trong [`sensor.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/events/sensor.yaml).

5. **Lỗ hổng NetworkPolicy ở `build`, `evidently`, `operations`: mở port `443` tới toàn bộ mạng private nội bộ & thiếu NetworkPolicy cho `deploy`/`training` trên `mlops-paas-execution`** *(Đã khắc phục)*
   - [`build/network-policy.yaml#L39-L51`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/build/network-policy.yaml#L39-L51), [`evidently/network-policy.yaml#L39-L51`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/evidently/network-policy.yaml#L39-L51), và [`operations/network-policy.yaml#L39-L51`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/operations/network-policy.yaml#L39-L51) đã bỏ `port: 443` khỏi rule `0.0.0.0/0` (chỉ giữ `port: 6443`, và thu hẹp `port: 443` cho `kubernetes.default.svc` `10.43.0.1/32`), giúp khôi phục hiệu lực chặn `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` trên port `443`.
   - Đã bổ sung `np-mlops-paas-deploy-execution` ([`deploy/network-policy.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/deploy/network-policy.yaml)) và `np-mlops-paas-training-execution` ([`training/network-policy.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/training/network-policy.yaml)) trong `mlops-paas-execution`, đồng thời gắn `podMetadata.labels` tương ứng cho các template trong [`deploy/workflow.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/deploy/workflow.yaml) và [`training/workflow.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/training/workflow.yaml) (chỉ mở DNS, K8s API `443`/`6443`, và Control Plane `8000`).

6. **`onExit: notify-build-exit` chạy cả khi build thành công → bắn HTTP 400 + 3 lần retry thừa** *(Đã khắc phục)*
   - [`build/workflow.yaml#L23,L283-L320`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/build/workflow.yaml#L23) đã đổi `onExit` sang `build-exit-handler` (steps template) với điều kiện `when: "{{workflow.status}} != Succeeded"` trước khi gọi `notify-build-exit`, đồng thời bổ sung `--connect-timeout 5` và `--max-time 15` cho `curl`.

7. **Callback exit của `training` và `delete` thiếu `retryStrategy`, timeout & `--fail-with-body`; thiếu `nodeSelector`** *(Đã khắc phục)*
   - [`training/workflow.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/training/workflow.yaml) (`report-status`, `report-cancellation`) và [`deploy/workflow.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/deploy/workflow.yaml) (`notify-delete-exit`) đã được bổ sung `retryStrategy` (`limit: "5"`, backoff `2s -> 120s`), `--connect-timeout 5`, `--max-time 15` và `--fail-with-body`.
   - Đã bổ sung `nodeSelector: {workload-type: worker}` cho các pod nhẹ của [`operations/workflow.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/operations/workflow.yaml) (`stopped`, `submit`, `reconcile`) và [`training/workflow.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/training/workflow.yaml) (`wait-training`, `report-status`, `cancel-training`, `report-cancellation`).

8. **Luồng `/delete` thiếu xác thực `tenant_id` & ownership** *(Đã khắc phục)*
   - [`cleanup_backends.py#L45-L54`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/infrastructure/execution/cleanup_backends.py#L45-L54) đã gửi kèm `tenant_id` (`project.owner.tenant_id`) trong payload `/delete`.
   - [`sensor.yaml#L137-L157`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/events/sensor.yaml#L137-L157): `delete-dep` đã lọc `body.tenant_id` (`^T-<uuid>$`) và kiểm tra mọi phần tử trong `body.container_names` khớp `^deploy-<uuid>$`, đồng thời truyền `tenant_id` vào `delete-workflow-trigger`.
   - [`deploy/workflow.yaml#L278-L350`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/deploy/workflow.yaml#L278-L350): `delete-runtime` chạy Python client qua K8s API (với `nodeSelector: {workload-type: worker}`), verify cả `Deployment` và `Service` khớp `mlops-paas.io/tenant-id` & `mlops-paas.io/project-id` và dùng `preconditions.uid` trước khi xóa.

9. **Dư thừa `harbor-base-pull-dockerconfig` trong `build/workflow.yaml` (và làm rõ `imagePullSecrets` cho Harbor Public)** *(Đã khắc phục)*
   - Đã xóa volume `harbor-base-pull` (`harbor-base-pull-dockerconfig`) và `volumeMounts` tương ứng khỏi [`build/workflow.yaml`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/build/workflow.yaml#L51-L58) vì không có `ExternalSecret` nào tạo secret này và các project Harbor `mlops-paas` / `user-images` đang để Public.
   - Giữ nguyên chế độ pull Public cho `build/workflow.yaml` và `evidently/workflow.yaml` (tránh gắn `imagePullSecrets` dùng robot chỉ giới hạn ở `user-images` lên các pod pull từ `mlops-paas`).

---

## Phần 2: Cấu hình dư thừa & luồng cũ còn tồn đọng (Legacy Leftovers)

| Thành phần | Vị trí | Tình trạng thực tế |
| --- | --- | --- |
| **Luồng `/cancel-build` *(Đã xóa)*** | `eventsource.yaml`, `sensor.yaml`, `job_ops.py`, `configmap.yaml`, `settings/base.py`, `k8s/verify/utils.py` | **Đã gỡ bỏ hoàn toàn.** `ArgoBuildBackend.cancel()` đi qua `/reconcile` (`reconcile_build_stop`). |
| **Luồng `/cancel-train` *(Đã xóa)*** | `argo_backends.py`, `deletion.py`, `executions.py`, `eventsource.yaml`, `sensor.yaml`, `training/workflow.yaml`, `job_ops.py` | **Đã thống nhất qua `/reconcile` (`stop=True`).** `ArgoTrainingBackend.cancel()` và `deletion.py` đều đi qua `/reconcile`, đã gỡ `/cancel-train` (`mlops-paas-training-cancel-template`). |
| **Luồng `/delete` *(Đã xóa)*** | `cleanup_backends.py`, `eventsource.yaml`, `sensor.yaml`, `deploy/workflow.yaml`, `deploy/rbac.yaml`, `deploy/external-secrets.yaml` | **Đã gỡ bỏ hoàn toàn.** `reconcile(deployment, stop=True)` xác nhận dừng và xóa runtime trước, sau đó `ArgoProjectCleanupBackend.run()` xóa ảnh Harbor và hoàn tất xóa trực tiếp. |
| **Mount & env cũ cài `pip` lúc runtime trong `deploy/workflow.yaml`** | [`deploy/workflow.yaml#L141-L144,L166-L168`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/deploy/workflow.yaml#L141-L144), [`argo_backends.py#L293-L294`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/infrastructure/execution/argo_backends.py#L293-L294), [`sensor.yaml#L101-L103`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/events/sensor.yaml#L101-L103) | Mount `dynamic-libs` (`/app/libs`), `pip-cache` (`/root/.cache/pip`), gửi trùng cả `image_uri` & `image_name`, `sensor.yaml` vẫn cho port `3000` (BentoML cũ, trong khi `deploy/network-policy.yaml` chỉ mở `5001/5002`), lặp 2 bộ label (`tenant`/`project`/`model-version` và `mlops-paas.io/*`). |
| **Env & template trùng lặp trong `training/workflow.yaml`** | [`training/workflow.yaml#L44-L45,L173-L505`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/training/workflow.yaml#L173-L505) | Mặc định `input_contract: legacy`, truyền `S3_SOURCE_URI`/`S3_TRAINING_DATA_URI`/`MODEL_VERSION` (`""`)/`REQUIREMENTS_TEXT` từ luồng cũ; nhân đôi ~160 dòng YAML giữa `cpu-train-job` và `gpu-train-job`. |
| **Env dư/lệch trong `evidently/workflow.yaml`** | [`evidently/workflow.yaml#L43-L44,L66-L67,L74-L75,L86-L87`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/evidently/workflow.yaml#L43-L44) | `DRIFT_REPORTS_S3_PREFIX` không được `services/evidently` đọc; `HTML_PUBLIC_URL` luôn gửi `""`; `control_plane_internal_url` default sai namespace (`http://mlops-paas-control-plane:8000` thiếu `.mlops-paas-core.svc.cluster.local`); `DRIFT_THRESHOLD` bị hardcode `"0.6"`. |
| **Image tag chưa nhất quán / chưa pin** | `build/workflow.yaml` (`kaniko:latest`, `curl:8.8.0`), `training/workflow.yaml` (`curl:8.7.1`) | Kaniko dùng `:latest`, còn `curlimages/curl` lệch version giữa `8.7.1` và `8.8.0`. |

---

## Phần 3: Thiếu đồng bộ với kiến trúc hiện tại & điểm cần nâng cấp

1. **`job_ops.py:reconcile` hỗ trợ `observe` (`stop=False`) cho `build` và `deployment`** *(Đã hoàn thiện)*
   - [`job_ops.py#L212-L340`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/operations/scripts/job_ops.py#L212-L340) đã cho phép `reconcile` với `stop=False` cho cả `build` (kiểm tra Workflow `build-<id>`, fallback label selector cho workflow/pod cũ) và `deployment` (kiểm tra Workflow `deploy-<id>` và `Deployment` trong `mlops-paas-serving` qua `availableReplicas >= 1` kể cả khi Workflow đã bị TTL GC).
2. **`single-node.yaml` (Training Runtime) thiếu `sizeLimit` trên `emptyDir` và giới hạn RAM chặt ở `prepare-input`**
   - [`single-node.yaml#L49-L54`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/runtimes/training/single-node.yaml#L49-L54): `training-work`, `training-output`, `training-model` không đặt `sizeLimit` → script của user ghi file lớn có thể làm cạn ephemeral storage của node.
   - `prepare-input` ([`single-node.yaml#L66-L68`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/runtimes/training/single-node.yaml#L66-L68)) chỉ có `limits.memory: 256Mi`, khá sát ngưỡng khi tải & giải nén archive workspace `256MiB`.
3. **Thiếu `securityContext` trên các workflow ngoài `single-node.yaml`**
   - `single-node.yaml` đã chuẩn hóa `runAsNonRoot: true`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `seccompProfile: RuntimeDefault`, trong khi `deploy/workflow.yaml` (serving pods chạy code user), `evidently/workflow.yaml`, `operations/workflow.yaml`, `build/workflow.yaml` chưa đồng bộ `securityContext`.
4. **Single Point of Failure ở `EventBus` (NATS)**
   - [`events/eventbus.yaml#L9`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/events/eventbus.yaml#L9) đang chạy `replicas: 1` và không có `persistence` → nếu pod NATS restart đúng lúc có burst webhook từ Celery, event đang bay trên bus có thể bị mất.

---

## Phần 4: Lộ trình đề xuất tối ưu

### Đợt 1 — Vá lỗi P0/P1 & Khép kín bảo mật (Ưu tiên cao nhất)
- [x] Sửa `argo_backends.py` truyền `MODEL_URI="/app/model_artifact"` và bổ sung `TENANT_ID` trong `deploy/workflow.yaml`.
- [x] Hạ `readinessProbe.failureThreshold` từ `150` xuống `3`.
- [x] Tách mức RAM cho DL (`2Gi`) vs ML (`1Gi`).
- [x] Nâng PVC `workspace` của `build/workflow.yaml` lên `10Gi` kèm `volumeClaimGC: {strategy: OnWorkflowCompletion}` và pin Kaniko `v1.23.2` thay cho `:latest`.
- [x] Thêm `ttlStrategy` + `podGC` cho 4 workflow chính (`build`, `deploy`, `evidently`, `training`) và `sensor.yaml` triggers.
- [x] Thêm điều kiện tránh chạy `notify-build-exit` khi `Succeeded`, thêm `retryStrategy` + timeout + `nodeSelector: {workload-type: worker}` cho toàn bộ exit/ops steps.
- [x] Siết lại NetworkPolicy ở `build`, `evidently`, `operations`: tách port `6443` riêng cho K8s API và **không** mở `0.0.0.0/0` port `443` đè lên luật chặn RFC1918; bổ sung Egress NetworkPolicy cho pod `deploy` & `training` trong `mlops-paas-execution`.

### Đợt 2 — Dọn dẹp luồng chết & thống nhất kiến trúc
- [x] Xóa hẳn `/cancel-build` (đã chết 100%).
- [x] Thống nhất `ArgoTrainingBackend.cancel()` và `catalog/services/deletion.py` đi hoàn toàn qua `/reconcile` (`stop=True`), sau đó gỡ `/cancel-train` (`mlops-paas-training-cancel-template`) và gỡ luôn `/delete` khi `reconcile(deployment, stop=True)` đã xác nhận dừng hết runtime.
- [x] Gỡ các env/mount legacy (`dynamic-libs`, `pip-cache`, `DRIFT_REPORTS_S3_PREFIX`, `HTML_PUBLIC_URL`, port `3000`, `image_uri` trùng) và đồng bộ `curlimages/curl:8.8.0` + `imagePullSecrets` + `sizeLimit` trên `single-node.yaml`.

### Đợt 3 — Hoàn thiện giám sát
- [x] Mở rộng `job_ops.py:reconcile` hỗ trợ `observe` (`stop=False`) cho `build` và `deployment` để khép kín cơ chế self-healing khi callback bị mất.
