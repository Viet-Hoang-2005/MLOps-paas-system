# Nhật ký Thay đổi

Tài liệu này ghi nhận các thay đổi mã nguồn có ảnh hưởng đến kiến trúc, contract và vận hành hệ thống MLOps.

## [Unreleased] - 2026-09-15

### Changed

- Tái cấu trúc schema first-party của Control Plane cho hướng Continuous Training; toàn bộ bảng thuộc schema `control_plane`.
- Tạo app nghiệp vụ `continuous_training` tại package `apps/ct`, giữ Django app label `ct` và tên bảng `ct_*`.
- Tạo `production_predictionrecord` làm nguồn dữ liệu production thống nhất cho API production-data, Evidently và automatic drift.
- Consumer không còn chạy `CREATE TABLE` hoặc `ALTER TABLE`. Consumer xác thực cặp `project_id`/`model_version_id` từ Kafka bằng `INSERT ... SELECT`, chống replay qua `public_id`, và bỏ qua event cross-project.
- Hợp nhất transactional outbox vào `observability_eventoutbox`. Kafka publisher chỉ claim event `kafka`; Consumer dispatcher chỉ claim event `webhook/automatic_drift`, dùng lease `FOR UPDATE SKIP LOCKED` và exponential backoff.
- Hợp nhất audit registry/training vào `observability_lifecycleevent`; endpoint lịch sử Registry và Training vẫn giữ JSON response hiện có.
- Evidently truy vấn `control_plane.production_predictionrecord` theo model version; Consumer và Evidently nhận `DB_SCHEMA=control_plane` từ Compose/Kubernetes.
- Bổ sung các liên kết nullable phục vụ Continuous Training cho TrainingJob, ModelMetric, Build, DriftMonitor và DriftRun; các trường lifecycle cũ vẫn được giữ để đảm bảo chức năng hiện tại.

### Added

- Thêm schema chuẩn bị cho Continuous Training: policy, dataset snapshot, evidence window/sample, label budget/request/feedback/ledger, maintenance decision/run/step attempt và evaluation gate.
- Thêm constraint và index cho probability/threshold/latency, quota nhãn, policy active duy nhất theo project, maintenance run active duy nhất theo project, idempotency và quan hệ CT.
- Thêm lệnh reset local `reset_control_plane_schema`: tái tạo schema `control_plane`, chỉ xóa bốn bảng legacy first-party trong `public`, giữ nguyên schema `mlflow`.
- Thêm kiểm thử cho constraint CT, production-data selector, outbox claim và Consumer ingestion.

### Removed

- Bỏ các bảng legacy do Consumer tự quản lý: `paas_production_logs`, `mlops_inference_events`, `mlops_production_data` và `paas_automatic_drift_outbox` khi clean reset local.
- Bỏ bảng audit riêng `registry_registryevent` và `training_trainingjobevent`.

### Compatibility

- Kafka inference event và trường `confidence` không đổi; các trường probability/calibration mới đang nullable và chưa yêu cầu producer điền.
- Chưa triển khai API hay workflow tạo evidence window, cấp nhãn, retraining, evaluation gate hoặc promotion tự động; thay đổi hiện tại chỉ chuẩn bị schema và contract.
