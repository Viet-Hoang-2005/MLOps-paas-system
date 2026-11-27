# Báo Cáo Rà Soát & Đề Xuất Tối Ưu `control-plane`

Báo cáo tổng hợp kết quả kiểm tra toàn bộ 12 apps và tầng `infrastructure/` trong [`services/control-plane/src/`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src) (đối chiếu chéo với `web/src/`, `k8s/`, `docker-compose.yml`, `model-server`, `consumer`, `evidently`, `training-runner`).

---

## Phần 1: Các bug tiềm ẩn cần xử lý (phân loại theo mức độ)

> [!CAUTION]
> Các mục **P0 (Nghiêm trọng)** dưới đây có thể gây lỗi trực tiếp trên production K3s, khóa vĩnh viễn quota/workspace người dùng, hoặc lỗ hổng phân quyền/bảo mật.

### P0 — Nghiêm trọng (Cần xử lý ngay)

1. **Regex webhook Deployment từ chối 100% callback deploy trên production Argo (HTTP 400)**
   - [`job_ops.py#L61-L62`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/operations/scripts/job_ops.py#L61-L62) tạo Workflow tên `deploy-<deployment_uuid>`, trong khi [`webhooks.py#L59-L62`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/deployment/api/webhooks.py#L59-L62) ép regex `r"deploy-model-job-[a-z0-9-]{1,100}"`.
   - *Hệ quả:* Mọi deployment trên K3s đều bị 400, treo `deploying` 33 phút rồi chuyển sang `unconfirmed`, chặn luôn các lần deploy tiếp theo của project.
2. **Health probe cho model `keras` gửi nhầm `GET` thay vì `POST` (luôn fail readiness / unhealthy)**
   - [`argo_backends.py#L275-L276`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/infrastructure/execution/argo_backends.py#L275-L276) và [`docker_backends.py#L225`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/infrastructure/execution/docker_backends.py#L225) xếp `keras` vào BentoML `deep-learning-serving` (chỉ nhận `POST /health`), nhưng [`runtime_health.py#L25`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/infrastructure/runtime_health.py#L25) chỉ check `{"pytorch", "tensorflow"}` (thiếu `"keras"`).
3. **Khóa vĩnh viễn quota & workspace khi Argo TrainingJob hủy/lỗi trước khi container `node` kịp chạy**
   - Khi pod chết ở pha `Pending`/init, [`job_ops.py#L227-L239`](file:///d:/AI%20Models/mlops-paas-system/k8s/argo/workflows/operations/scripts/job_ops.py#L227-L239) trả `never_started=False` và không có `started_at`. [`quota.py#L136-L137`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/training/services/quota.py#L136-L137) trả `False`, khiến `TrainingQuotaReservation.active=True` vĩnh viễn → user bị chặn mãi bởi `TrainingConcurrencyExceeded`.
   - Tương tự, [`confirm_training_cancellation`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/training/tasks.py#L220-L252) (qua `TrainingCancellationWebhookEndpoint`) chuyển job sang `cancelled` mà không settle `TrainingQuotaReservation` / `LocalTrainingReservation`, thậm chí cho phép `delete_training_job` xóa row job để lại reservation `active=True` mồ côi.
4. **Tài khoản đã soft-delete vẫn gọi được API Key, MLflow & Model Server; `auth_provider` bị ghi đè qua Profile**
   - [`deactivate_user_account`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/auth/services/account_lifecycle.py#L17-L31) chưa thu hồi `UserAPIKey`, chưa blacklist refresh tokens, chưa tăng `session_version`, và [`AccountDeleteEndpoint`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/auth/api/account_endpoints.py#L33-L36) chưa xóa cookie refresh.
   - [`apps/mlflow/auth.py#L85-L95`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/mlflow/auth.py#L85-L95) và [`model-server/src/database.py#L82-L90`](file:///d:/AI%20Models/mlops-paas-system/services/model-server/src/database.py#L82-L90), [`#L141-L152`](file:///d:/AI%20Models/mlops-paas-system/services/model-server/src/database.py#L141-L152) không lọc `user.is_active = TRUE`.
   - [`UserSerializer`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/auth/api/serializers.py#L118-L132) khai báo `auth_provider` trong `fields` nhưng quên đưa vào `read_only_fields` → user có thể tự sửa `auth_provider` qua `PUT /api/auth/profile/`.
5. **Nguy cơ Deadlock PostgreSQL do đảo thứ tự khóa `select_for_update()`**
   - [`execute_build`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/deployment/tasks.py#L101-L102) và [`versions.py#L83-L84`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/registry/services/versions.py#L83-L84) khóa `ModelProject` rồi gọi `Build.objects.select_for_update().select_related("project", "project__owner")` **không có `of=("self",)`** → khóa `CustomUser` sau `ModelProject`.
   - Ngược lại, [`_submit_job_atomic`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/training/services/jobs.py#L23-L26) và [`apply_observation`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/observability/services/executions.py#L398-L400) khóa `CustomUser` **trước** `ModelProject`.
   - [`mark_deployment_unconfirmed`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/deployment/tasks.py#L434) khóa `Deployment` + `ModelVersion` mà không khóa `ModelProject` trước.
6. **Xóa Project có Argo Build đang chạy luôn bị `delete_failed`**
   - [`apps/catalog/services/deletion.py#L90-L93`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/catalog/services/deletion.py#L90-L93) ép `ArgoBuildBackend.cancel()` phải trả `confirmed=True`, nhưng [`argo_backends.py#L152-L165`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/infrastructure/execution/argo_backends.py#L152-L165) luôn trả `{"dispatched": True}` (không bao giờ có `confirmed`) → ném `ValidationError` làm hỏng tiến trình xóa project.

### P1 — Mức độ cao (Race conditions, rò rỉ tài nguyên, lỗi dữ liệu)

7. **Lost-update trên `TrainingJob.tracking` có thể xóa sạch `output_contract: 2`**
   - Các view MLflow ([`metrics.py#L80-L88`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/mlflow/views/metrics.py#L80-L88), [`runs.py#L121-L127`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/mlflow/views/runs.py#L121-L127)) đọc-sửa-ghi `job.tracking` không có khóa. Request MLflow đến trễ ghi đè `tracking` sẽ xóa mất `output_contract: 2` / `output_index_queued_at` do `output_finalization` vừa ghi.
   - Ngoài ra, [`finalize_output`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/training/services/output_finalization.py#L42-L56) cho phép chạy 3600s nhưng debounce chỉ 600s → archive lớn (>10 phút) bị `scan_job_executions` đẩy chạy 2 worker `finalize_output` song song.
8. **Rò rỉ OCI image trên Harbor ở 3 nhánh**
   - Khi Argo build lỗi sau bước `push-image` hoặc bị hủy, [`webhooks.py#L217-L233`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/deployment/api/webhooks.py#L217-L233) và [`tasks.py#L146,L235`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/deployment/tasks.py#L146) truyền `delete_image=False` vì `build.image_uri == ""`.
   - Khi xóa `ModelVersion`, [`apps/registry/services/deletion.py#L47-L48`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/registry/services/deletion.py#L47-L48) chỉ gọi `delete_tag` mà không xóa untagged manifest/layers (`delete_artifact`).
   - Khi `register_successful_build` promote tag `:vN` thành công rồi fail ở `_commit_registration` ([`versions.py#L158-L179`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/registry/services/versions.py#L158-L179)), tag `:vN` không được rollback.
9. **Cache invalidation chạy trước khi DB commit & giữ DB lock khi gọi network I/O**
   - `_mark_deployment_succeeded` ([`tasks.py#L80`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/deployment/tasks.py#L80)) gọi `invalidate_model_server_cache` bên trong outer `transaction.atomic()` (trước commit) → `model-server` có thể đọc lại trạng thái cũ và cache sai 30s.
   - [`ArgoBuildBackend.run`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/infrastructure/execution/argo_backends.py#L145-L150) giữ `select_for_update()` trong lúc gửi HTTP POST `trigger()` (và không check `status == "cancelled"`).
   - [`create_monitor`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/drift/services/monitors.py#L60-L103) và [`mutate_training_output`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/training/services/outputs.py#L130-L239) gọi `storage.put()` ngay trong `transaction.atomic()` đang giữ `FOR UPDATE`.
10. **Auto-retry bị vô hiệu trong `execute_deployment` & lỗ hổng xóa `DriftMonitor` / `DriftRun`**
    - [`execute_deployment`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/deployment/tasks.py#L348-L405) khai báo `autoretry_for=(ConnectionError, TimeoutError)` nhưng dòng 391-393 lại đánh dấu `status="failed"` ngay lần đầu → lần retry kế tiếp thấy `status == "failed"` rồi return sớm.
    - `DriftMonitor` bị đặt `deletion_requested=True` khi Argo stop chưa confirm sẽ treo vĩnh viễn (không có reconciler nào resume lại trong [`ArgoRuntimeStopEndpoint`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/observability/api/executions.py#L83-L92), vẫn cho `PATCH`/`PUT`).
    - Automatic drift ([`automatic.py#L43-L52`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/drift/services/automatic.py#L43-L52)): nếu user tăng `trigger_threshold`, `current_count // threshold` bị trùng bucket cũ → âm thầm bỏ qua lần trigger nhưng vẫn nâng `last_automatic_trigger_count`.
    - `DriftRun.idempotency_key` đang đặt `unique=True` toàn cục ([`apps/drift/models.py#L56`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/drift/models.py#L56)) nhưng `get_or_create` lọc theo `monitor` → dùng lại key trên monitor/tenant khác gây `IntegrityError` (HTTP 500).
    - Race giữa `skipped` drift run (không upload `report.html`) và `reconcile` watcher: nếu watcher bắt exit code `0` trước webhook `skipped`, watcher thấy thiếu file S3 và đánh dấu `failed` ([`executions.py#L377-L392`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/observability/services/executions.py#L377-L392)).
11. **Lỗi HTTP 500 / thiếu kiểm soát đầu vào ở nhiều endpoint**
    - [`model_observability`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/observability/services/models.py#L29-L34) không bọc `try/except` quanh Prometheus query → Prometheus down là trang observability 500 (đồng thời query `paas_prediction_latency_seconds_count` là số request chứ không phải latency, và thiếu filter `tenant_id`).
    - [`APIKeyRegenerateEndpoint`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/access/api/endpoints.py#L47) dùng `.get()` thay vì `get_object_or_404()` (500 thay vì 404); tạo API key trùng tên (kể cả trùng tên key đã revoke) gây 500 do `UniqueConstraint` không có `condition=Q(revoked_at__isnull=True)`.
    - [`MLflowArtifactsProxyView.delete`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/mlflow/views/artifacts.py#L600) dùng `relative_path__startswith=f"artifacts/{rel_path}"` (thiếu `/` → xóa `model` sẽ xóa nhầm luôn `model_v2`).
    - [`apps/mlflow/auth.py#L97-L100`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/mlflow/auth.py#L97-L100) đặt `authentication_classes = ()` nên nhánh xác thực Bearer JWT luôn gặp `AnonymousUser` (401).
    - [`ReadyEndpoint`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/observability/api/endpoints.py#L25-L43) (`AllowAny`) trả thẳng raw `str(exc)` của PostgreSQL/Redis ra ngoài.
    - [`test_preview_lifecycle.py#L309`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/catalog/tests/test_preview_lifecycle.py#L309) đang fail xác định (`assert artifact.uri != monitor.reference_uri`) do commit `3ccbd20e` chuyển sang tái sử dụng trực tiếp `artifact.uri` cho `DriftMonitor`.

### P2 — Hiệu năng, bộ nhớ & ổn định (N+1, RAM spikes)

12. **N+1 Queries nghiêm trọng trên các màn hình chính**
    - `GET /api/models/` ([`apps/catalog/api/endpoints.py#L37-L45`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/catalog/api/endpoints.py#L37-L45), [`serializers.py#L83-L140`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/catalog/api/serializers.py#L83-L140)): prefetch thừa `versions__deployments__endpoint` & `builds` không dùng, nhưng lại bắn 2–3 query/project và khởi tạo mới `boto3.client("s3")` cho từng asset.
    - `GET /api/registry/models/<id>/versions/` ([`apps/registry/api/serializers.py#L71,L89-L92`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/registry/api/serializers.py#L71)): 3 extra queries/version (`project`, `metrics`, `LifecycleEvent`) dù UI không render `metrics` hay `events`.
    - `GET /api/training-jobs/` ([`apps/training/api/serializers.py#L99,L197-L214`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/training/api/serializers.py#L99)): `public_outputs()` gọi `.filter()` phá vỡ `prefetch_related("outputs")`, thiếu `select_related("workspace")`, và khởi tạo `Fernet(...)` lặp lại cho từng dòng.
    - `GET /api/drift-monitors/`: `get_production_records` bắn `COUNT(*)` cho từng run thiếu count trong summary.
13. **Đọc toàn bộ file lớn vào RAM trong web worker / Celery**
    - Preview/Version CSV đọc tối đa **100 MiB** vào RAM + decode `str` trong Gunicorn ([`preview.py#L191-L193`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/catalog/services/preview.py#L191-L193), [`versions.py#L391,L575`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/registry/services/versions.py#L391)).
    - `workspaces.snapshot_input` ([`workspaces.py#L144,L173`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/training/services/workspaces.py#L144)) dùng `BytesIO` + `.getvalue()` chiếm ~512 MiB peak RAM cho workspace 256 MiB; [`snapshots.input_snapshot`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/training/services/snapshots.py#L18) cũng nạp tối đa 256 MiB vào Gunicorn RAM (và trả 500 trên job chưa submit).

---

## Phần 2: Các điểm dư thừa sót lại từ luồng cũ (Legacy Leftovers)

| Nhóm | Thành phần dư thừa | Vị trí | Hiện trạng / Ghi chú |
| --- | --- | --- | --- |
| **Endpoints không có caller (FE/BE)** | `POST /api/models/training-projects/`<br>`GET /api/models/<id>/preview/reference-preview/`<br>`GET /api/models/<id>/label-mapping/`<br>`POST /api/registry/versions/<id>/smoke-test/`<br>`GET/POST /api/registry/models/<id>/aliases/`<br>`POST .../aliases/<name>/predict/`<br>`GET /api/endpoints/<id>/logs/`<br>`POST /api/2.0/mlflow/artifacts/upload-url` | [`catalog/api/urls.py`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/catalog/api/urls.py)<br>[`registry/api/urls.py`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/registry/api/urls.py)<br>[`deployment/api/urls.py`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/deployment/api/urls.py)<br>[`mlflow/urls.py#L38`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/mlflow/urls.py#L38) | `web/src` không gọi bất kỳ endpoint nào trong nhóm này. `EndpointLogsEndpoint` thậm chí trả rỗng trên Argo và bỏ qua kiểm tra label ownership trên Docker. |
| **6 route MLflow bị lặp lồng nhau** | `/api/2.0/mlflow/api/2.0/mlflow-artifacts/...` & `/api/2.0/mlflow/mlflow-artifacts/...` | [`apps/mlflow/urls.py#L39-L60`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/mlflow/urls.py#L39-L60) | Trùng hoàn toàn 6 route root ở [`config/urls.py#L35-L40`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/config/urls.py#L35-L40); chỉ còn test cũ gọi vào. |
| **Legacy polling tasks đã chết** | `poll_training_job_status`, nhánh non-watch trong `execute_training_job` / `cancel_training_job`, `confirm_training_cancellation`, `poll_drift_run_status`, `ArgoBackend.poll` | [`training/tasks.py#L26-L252`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/training/tasks.py#L26-L252)<br>[`drift/tasks.py#L24-L183`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/drift/tasks.py#L24-L183) | `quota.py` và `local_resources.py` đã ép bật `TRAINING_EXECUTION_WATCH_ENABLED=True` nên nhánh non-watch của Training hoàn toàn unreachable trên mọi môi trường thật. |
| **Cột DB chết / trùng lặp** | `Build`: `log_uri`, `log_tail` (+ `BuildSerializer.logs`)<br>`TrainingJob`: `trigger_kind`, `baseline_version`, `dataset_snapshot`, `recipe_version`, `mlflow_artifact_uri`, `mlflow_run_id`, `celery_task_id`, `started_at` trùng `runtime_started_at`<br>`DriftMonitor/Run`: `detector_version`, `detector_config`, `current_data_uri`, `report_manifest_uri` | [`deployment/models.py#L62-L64`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/deployment/models.py#L62-L64)<br>[`training/models.py#L130-L181`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/training/models.py#L130-L181)<br>[`drift/models.py#L16-L51`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/drift/models.py#L16-L51) | Các cột không đọc/không ghi ở production code; riêng `BuildSerializer` vẫn trả `logs` (tới 20 KB/row) cho `GET /api/builds/` dù FE chỉ dùng `/builds/<id>/logs/`. |
| **Legacy training storage & input contract** | `input_contract != "workspace"`, `data_snapshot_uri`, `storage_layout="project"`, `storage_project_id`, `TrainingStorageCopy`, `storage_migration.py` | [`training/models.py#L130-L163`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/training/models.py#L130-L163)<br>[`storage_migration.py`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/training/services/storage_migration.py) | Mọi job mới chỉ đi qua `drafts.py` (`storage_layout="tenant"`, `input_contract="workspace"`, `data_snapshot_uri=""`). |
| **13 bảng `apps/ct` & `RegistryAlias` / `ModelMetric`** | 13 bảng `ct_*` không có service/API/task; `RegistryAlias` + `routing.py`; `ModelMetric` không được FE dùng | [`apps/ct/models.py`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/ct/models.py)<br>[`registry/services/routing.py`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/registry/services/routing.py) | Mỗi lần xóa `ModelProject` hoặc `ModelVersion` phải bắn thêm 10–15 câu `EXISTS`/`DELETE` vô ích vào 13 bảng `ct_*` trống. |
| **Dead code / Redis / Settings** | `MODEL_SERVER_INTERNAL_URL`, `GITHUB_OAUTH_REDIRECT_URI`, `MLFLOW_TRACKING_URI`, Redis DB 1 `training_metrics:*` (0 consumer, không bao giờ xóa), `DeploymentBackend.health()`, `active_user_by_email`, `"kubeflow"` trong `factory.py`, `WorkspaceAsset` fallback ở `snapshots.py:272` | [`config/settings/base.py`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/config/settings/base.py)<br>[`mlflow/views/metrics.py#L91-L104`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/mlflow/views/metrics.py#L91-L104) | Làm nhiễu cấu hình ở `.env.example`, `docker-compose.yml` và `k8s/.../configmap.yaml`. |

---

## Phần 3: Các luồng chưa đồng bộ với kiến trúc hiện tại

1. **Giám sát vòng đời thực thi (Execution Supervision) lệch pha giữa Docker và Argo**
   - `TrainingJob` và `DriftRun` dùng durable watch (`scan_job_executions`), nhưng trên K3s production [`configmap.yaml#L46`](file:///d:/AI%20Models/mlops-paas-system/k8s/workloads/base/control-plane/configmap.yaml#L46) vẫn để `DRIFT_EXECUTION_WATCH_ENABLED="false"` → mọi drift run xong trên K3s bị kẹt `cleanup_pending` mãi mãi vì `DriftRunWebhookEndpoint` luôn gán `observation_status="cleanup_pending"`.
   - `Build` và `Deployment` ở Docker có `scan_local_executions` (5s/lần), nhưng **Argo Build không có timeout/reconciler nào** và **Argo Deployment chỉ trông chờ 1 countdown Celery 33 phút không bền vững**.
   - Hai module [`local_containers.py`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/infrastructure/execution/local_containers.py) và [`job_containers.py`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/infrastructure/execution/job_containers.py) cùng quản lý Docker container nhưng hành vi ownership check/stop/remove không nhất quán.
2. **EventOutbox (`delivery_kind="kafka"`) bị đứt mạch**
   - `control-plane` ghi event `identity.events` (`tenant.disabled`), `registry.events`, `deployment.events` vào `EventOutbox`, nhưng:
     - **Chưa có bất kỳ consumer nào** đọc 3 topic này (`consumer` chỉ đọc `mlops_paas_production_data`).
     - **`publish_outbox` không nằm trong `CELERY_BEAT_SCHEDULE`** → nếu lần gửi đầu lỗi (không phải `BufferError`) hoặc broker tạm gián đoạn lúc `on_commit`, event nằm kẹt trong bảng `observability_eventoutbox` cho tới khi có sự kiện khác tình cờ gọi `enqueue_event`.
3. **AlertWebhookEndpoint chưa nối dây & dễ spam**
   - [`monitoring.yaml#L87-L105`](file:///d:/AI%20Models/mlops-paas-system/k8s/gitops/production/applications/addons/monitoring.yaml#L87-L105) không cấu hình webhook gửi tới `/internal/webhooks/alerts/`. Bản thân endpoint ([`apps/notifications/api/webhooks.py#L24-L87`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/notifications/api/webhooks.py#L24-L87)) không deduplicate theo Alertmanager `fingerprint`, tạo lặp notification mỗi `repeat_interval`, và không kiểm tra `tenant_id` khớp `project.owner.tenant_id`.
   - Ngược lại, khi `TrainingJob` hoặc `DriftRun` kết thúc qua watcher (`executions.py:_finish`), hệ thống **không gọi** `notify_training_result` / `notify_drift_result`.
4. **Sở hữu Reference CSV giữa `DriftMonitor` và `ModelVersion` chưa khép kín**
   - `create_monitor` gắn `ModelArtifact(kind="reference_data")` vĩnh viễn vào `ModelVersion` và chia sẻ `uri` với `DriftMonitor.reference_uri`, nhưng không có API thay thế/xóa `reference_data` artifact. Nếu user upload nhầm CSV rồi xóa monitor, `ModelArtifact` vẫn còn → tạo monitor mới với CSV sửa lỗi luôn bị HTTP 409.
   - Khi xóa `ModelVersion`, [`apps/registry/services/deletion.py#L127-L145`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/registry/services/deletion.py#L127-L145) gọi `delete_prefix(s3_prefix)` **trước** khi kiểm tra `shared`, và bảng kiểm tra `shared` quên kiểm tra `DriftMonitor.reference_uri`.
5. **Account Purge mâu thuẫn với Project Deletion**
   - [`purge_user_account`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/auth/services/account_lifecycle.py#L117-L135) gọi `request_project_deletion` → kéo theo `migrate_project_storage` copy + hash lại toàn bộ file training cũ sang tenant prefix, rồi ngay bước sau lại xóa chính các `TrainingJob` đó! Nếu 1 file cũ bị thiếu, cả tiến trình purge account bị kẹt vĩnh viễn.
6. **MLflow Proxy phá vỡ layering & lưu artifact "tàng hình"**
   - `apps/mlflow/views/` bỏ qua service layer (truy vấn thẳng ORM + `S3Storage` + Redis DB 1), `MLflowExperimentsCreateView` tạo thẳng `ModelProject` không qua `catalog`.
   - Artifact upload qua `MLflowArtifactsProxyView.put` tạo `TrainingOutput` không có `metadata.contract=2` nên **bị ẩn hoàn toàn** khỏi UI `outputs`, download và build model.
7. **Upload & Deletion bất đối xứng giữa các resource**
   - `ModelPreview` upload qua presigned S3 staging, còn `supplemental-artifacts` (`ModelVersion`) vẫn đẩy file tối đa 100 MiB qua Gunicorn multipart.
   - `ModelProject`, `Build`, `TrainingWorkspace`, `TrainingJob` đều xóa bất đồng bộ qua Celery + `reconcile_stalled_deletions`, nhưng **`ModelVersion` xóa đồng bộ trong HTTP `DELETE`** và không có reconciler → lỗi giữa chừng để lại zombie version.
   - `ArgoDeploymentBackend.deploy` vẫn truyền `s3://...` vào `model_uri` (dù image đã đóng sẵn `/app/model_artifact`) và quên truyền `TENANT_ID` trong `deploy/workflow.yaml`.

---

## Phần 4: Lộ trình đề xuất tối ưu các luồng nghiệp vụ

### Đợt 1 — Vá lỗi P0 & Khóa an toàn hệ thống (Ưu tiên cao nhất)
1. **Fix Argo Deployment callback & `keras` health probe**:
   - Sửa regex trong [`DeploymentWebhookEndpoint`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/deployment/api/webhooks.py#L59-L62) chấp nhận `deploy-<uuid>` (khớp `job_ops.py:61-62`).
   - Gom 1 helper duy nhất `is_dl_flavor(flavor)` (`{"pytorch", "tensorflow", "keras"}`) dùng chung cho `RuntimeHealthProbe`, `DockerDeploymentBackend`, `ArgoDeploymentBackend` và `model-server`.
2. **Khép kín bảo mật Soft-delete & Profile**:
   - Đưa `auth_provider` vào `read_only_fields` của `UserSerializer`.
   - Trong `deactivate_user_account`: khóa `CustomUser`, thu hồi `UserAPIKey` (`revoked_at=now`), tăng `session_version`, bulk-blacklist refresh tokens, xóa refresh cookie trong `AccountDeleteEndpoint`; bổ sung `user__is_active=True` trong `apps/mlflow/auth.py` và `model-server/src/database.py`.
   - Khi `purge_user_account` chạy, bỏ qua `migrate_project_storage`.
3. **Chuẩn hóa thứ tự khóa DB & tách I/O ra khỏi `transaction.atomic()`**:
   - Quy ước 1 thứ tự khóa toàn hệ thống: **`CustomUser` → `TrainingWorkspace` → `ModelProject` → `ModelVersion` → `Build` / `Deployment` / `TrainingJob` / `DriftMonitor`**.
   - Bắt buộc dùng `select_for_update(of=("self",))` mọi nơi có `select_related(...)`.
   - Đưa toàn bộ `invalidate_model_server_cache`, Redis log writes, `ArgoBuildBackend.trigger()`, và `storage.put()` ra ngoài `transaction.atomic()` (hoặc `transaction.on_commit`).
4. **Chống kẹt Quota Training & Project Deletion trên Argo**:
   - Xử lý rõ trạng thái "workflow kết thúc trước khi container `node` chạy" trong `job_ops.py` / `quota.py`, bỏ `confirm_training_cancellation` (định tuyến cancel qua `ExecutionWatch`), và cấm xóa `TrainingJob` nếu vẫn còn reservation `active=True`.
   - Cho phép `execute_project_deletion` chờ Argo build stop thay vì ném `ValidationError`, và thu hẹp `project_has_unconfirmed_argo_stops` chỉ xét các runtime thực sự có thể đang sống (tránh fan-out workflow cho mọi row lịch sử).
   - Cập nhật assertion ở [`test_preview_lifecycle.py#L309`](file:///d:/AI%20Models/mlops-paas-system/services/control-plane/src/apps/catalog/tests/test_preview_lifecycle.py#L309) và sửa kiểm tra `shared` trước `delete_prefix` khi xóa `ModelVersion`.

### Đợt 2 — Thống nhất kiến trúc Execution, Drift & Storage
5. **Đồng nhất Durable Execution Watch trên cả Docker và Argo**:
   - Bật `DRIFT_EXECUTION_WATCH_ENABLED="true"` trên K3s `configmap.yaml`, xử lý `skipped` drift run (ghi `summary.json` gọn hoặc cho watcher nhận diện skip) và set `argo_stop_confirmed_at` khi `observed == "stopped"`.
   - Mở rộng `scan_job_executions` quản lý luôn **Argo `Build` và Argo `Deployment`** (thêm `activeDeadlineSeconds` + `retryStrategy` vào `build/workflow.yaml`, thay thế countdown 33 phút của `mark_deployment_unconfirmed`).
   - Hợp nhất `local_containers.py` và `job_containers.py` thành 1 adapter Docker duy nhất.
6. **Tối ưu luồng S3 & Upload (Giảm copy thừa & giảm RAM)**:
   - **Pre-check admission trước khi zip 256 MiB**: ở `run_workspace`, kiểm tra sơ bộ concurrency/quota/GPU trước khi enqueue `prepare_training_input` để trả HTTP 409 tức thì thay vì zip 256 MiB rồi mới fail với thông báo chung chung.
   - **Giảm copy S3 giữa Preview/Training → Build → Version**: chỉ snapshot vào `builds/{b}/inputs/` đúng 3 file mà `model-packager` cần (`source_artifact`/`training_output`, `label_mapping`, `input_schema`), còn `reference_data` / `source_code` / `insights` copy thẳng từ nguồn gốc khi `register_version` (hoặc tiến tới content-addressed blobs).
   - Chuyển `supplemental-artifacts` sang presigned S3 upload (như Preview) và chuyển các hàm đọc/preview CSV & `snapshot_input` sang streaming (`SpooledTemporaryFile` / `csv.reader`) thay vì đọc 100–256 MiB vào RAM.
7. **Chuyển `delete_model_version` & `delete_drift_monitor` sang async + reconciler**:
   - Dùng `delete_artifact` trên Harbor (tránh manifest mồ côi), vá `execute_deployment` retry logic, và nối cả `ModelVersion(deletion_requested=True)` + `DriftMonitor(deletion_requested=True)` vào `reconcile_stalled_deletions`.
   - Sửa auto-drift dùng monotonic counter/key thay vì `count // threshold`, và đổi `DriftRun.idempotency_key` thành `UniqueConstraint(fields=["monitor", "idempotency_key"])`.

### Đợt 3 — Tách bạch `TrainingJob.tracking`, MLflow, Outbox & Notifications
8. **Giải tải `TrainingJob.tracking` & dọn MLflow**:
   - Tách các cờ vận hành (`output_contract`, `output_index_queued_at`, `output_runtime_finished_at`, `logs_tail`) ra khỏi JSONField `tracking` (hoặc ngừng để MLflow view ghi đè `tracking` mà đọc summary bằng `DISTINCT ON` từ `TrainingJobMetric`/`Param`), xóa hoàn toàn race condition.
   - Bỏ 6 route MLflow trùng lặp trong `apps/mlflow/urls.py`, bỏ endpoint chết `artifacts/upload-url`, bỏ publish Redis DB 1 không ai đọc, sửa bug `startswith` khi xóa artifact và sửa JWT auth trong `apps/mlflow/auth.py`.
9. **Quyết định rõ ràng cho `EventOutbox (kafka)` và `AlertWebhookEndpoint`**:
   - Nếu muốn dùng `identity.events`/`deployment.events`: thêm `publish_outbox` vào `CELERY_BEAT_SCHEDULE` và nối consumer (VD: `model-server` lắng nghe `tenant.disabled` để xóa cache tức thì). Nếu chưa có consumer: ngừng ghi dòng `kafka` outbox để tránh tích tụ bảng DB.
   - Nối `notify_training_result` / `notify_drift_result` vào `executions.py:_finish`, thêm deduplication theo Alertmanager `fingerprint` (hoặc gỡ `AlertWebhookEndpoint` nếu chưa cấu hình Alertmanager).

### Đợt 4 — Dọn dẹp Legacy & Tối ưu hiệu năng truy vấn
10. **Cắt bỏ dead code, dead endpoints & slim schema**:
    - Xóa nhánh non-watch + `poll_training_job_status` + `poll_drift_run_status` sau khi chốt watcher.
    - Dọn các endpoint không có caller (`EndpointLogsEndpoint`, `aliases/*`, `smoke-test`, `training-projects`, `label-mapping`, `preview/reference-preview`), các cột DB chết (`Build.log_uri/log_tail`, bỏ `logs` khỏi `BuildSerializer`, 4 cột CT chết + `mlflow_artifact_uri/run_id` trên `TrainingJob`, 4 cột chết trên `DriftMonitor/Run`), và 3 biến môi trường không dùng (`MODEL_SERVER_INTERNAL_URL`, `GITHUB_OAUTH_REDIRECT_URI`, `MLFLOW_TRACKING_URI`).
    - Tạm bỏ qua 10–15 câu query vô ích vào 13 bảng `ct_*` khi xóa Project/Version cho đến khi phân hệ CT thực sự được triển khai.
11. **Xử lý triệt để N+1 & bảo vệ Observability**:
    - Dùng `Subquery` + `Prefetch(..., to_attr=...)` cho `GET /api/models/`, `GET /api/registry/models/<id>/versions/`, `GET /api/training-jobs/`, `GET /api/drift-monitors/`; tái sử dụng 1 instance `S3Storage` / `Fernet` thay vì tạo mới theo từng dòng.
    - Bọc `try/except` cho Prometheus queries trong `model_observability` (sửa query latency + thêm `tenant_id`), sanitize lỗi ở `/health/ready`, sửa race `drift_run_logs` (`offset + len(lines)`), và giới hạn/phân trang `ProductionDataEndpoint`.
