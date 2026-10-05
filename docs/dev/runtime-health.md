# Deployment lifecycle và API Health

## Contract

| Field | Giá trị | Ý nghĩa |
| --- | --- | --- |
| `Deployment.status` | `pending`, `deploying`, `succeeded`, `failed`, `stopped`, `unconfirmed` | Kết quả một lần triển khai |
| `Endpoint.health_status` | `unknown`, `healthy`, `unhealthy` | Quan sát API runtime |
| `Build.registration_status` | `unregistered`, `registering`, `registered`, `failed` | Đăng ký snapshot |

Vượt readiness mới ghi succeeded và đổi active_deployment. Candidate thất bại giữ
Running cũ. Callback lặp không hồi sinh failed/stopped; callback hợp lệ đến muộn có
thể xác nhận unconfirmed (thiếu kết quả không kết luận runtime lỗi). API lỗi/phục hồi
chỉ đổi health, không đổi lifecycle/Running/drift. Stop xóa Running pointer, health
unknown, timestamp/lease null. Gateway và prediction qua registry chỉ resolve Running
succeeded, không fallback image mẫu/version khác; health không tự chuyển phiên bản.

## Process nền thuộc Control Plane

- celery-beat: một scheduler, scan mỗi 15 giây. K8s một replica, Recreate; không
  scale Beat hoặc chạy thêm worker với -B.
- Production: celery-health-worker consume queue runtime-health, concurrency 2.
  Worker build/training chỉ consume celery để tách slot health.
- Local: celery-worker consume cả celery và runtime-health, concurrency 2 dùng
  chung. Không có container celery-health-worker riêng; task health có thể chờ
  khi worker bận. Beat vẫn riêng và còn lên lịch scan Build/Deploy mỗi 5 giây.

Cùng image; Beat và health worker production dùng config.settings.health, chỉ cần
Django key, DB/broker credentials. Hai process này không có Docker socket,
AWS/Harbor credentials hoặc Kubernetes token. Local dùng worker orchestration
hiện có (config.settings.local), không cấp thêm credential hay mount. Probe HTTP đến
ứng dụng runtime, không Docker stats, Pod phase hay gateway công khai. Metrics riêng.

Scanner chọn Running succeeded của project active. Lease PostgreSQL 30 giây. Token
delivery single-use đổi atomically sang token probe trước I/O để duplicate delivery
không probe đồng thời. Probe ngoài transaction; khi ghi khóa project → deployment →
endpoint và kiểm tra lại Running/lifecycle/token/lease. Stop, đổi Running hoặc xóa
project trong lúc probe khiến kết quả cũ bị bỏ qua.

Task chờ queue >15 giây hết hạn, soft timeout 8 giây/hard 10 giây, không autoretry
dài. Lease expiry phục hồi worker crash. Lỗi broker/DB/monitor không ghi thành lỗi
model; thiếu quan sát mới sẽ stale. ML GET /health; DL/BentoML POST /health với {}.
Connect/read timeout 1/2 giây, không retry/redirect/proxy môi trường, response ≤64 KiB,
stream deadline 5 giây. Healthy cần HTTP 200, status healthy, model_loaded true và
project_id/model_version_id khớp. Timeout, không kết nối, JSON lỗi, sai identity hoặc
chưa load → unhealthy. Không thêm lịch automatic drift.
Tham khảo [Celery periodic tasks](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html).

## API/Web

active_endpoint chứa registration của Build Running, health, last_checked_at. API
chỉ đọc DB, không probe theo request. Quan sát >45 giây/missing timestamp/non-succeeded
trình bày unknown, không xóa kết quả thô trong DB khi đọc.

Overview: Artifact → Build Image → Register model → API Health. Badge/bước health
dùng chung helper, xanh/đỏ/trung tính; EN/VI. Poll 5 giây khi foreground/có Running
succeeded, timestamp và clock freshness; lỗi fetch không giữ xanh. Không Running/
stopped: không kiểm tra, không poll health. Unhealthy giữ endpoint/snapshot/lịch sử.

## Rollout local do người dùng thực hiện

Migration deployment/0007_runtime_health chỉ đổi schema, không chuyển dữ liệu cũ.
Deployment healthy/unhealthy hoặc health stopped/deploying sẽ vi phạm constraint.
Dùng DB local sạch. Người dùng tự sao lưu/reset; agent không xóa volume/purge queue/
migrate DB đang chạy. Sau khi chuẩn bị DB/broker sạch và .env hợp lệ:

```bash
docker compose config --quiet
docker compose up -d --build control-plane celery-worker celery-beat model-server
docker compose logs --tail 80 celery-beat celery-worker
```

Control Plane migrate như hiện có; worker và Beat chờ migrate --check, không tự
migrate. Production dùng migration hook của Control Plane Application.

Smoke thủ công trên runtime test riêng:

1. Build/register/deploy: succeeded, Running đúng version, healthy/timestamp mới.
2. Đóng Web >30 giây: DB/API timestamp vẫn tiến lên.
3. Pause rồi unpause runtime test: health unhealthy → healthy, lifecycle succeeded
   và Running không đổi. Không gọi stop lifecycle cho phép thử phục hồi này.
4. Tắt celery-worker local >45 giây (production: health worker): API/Web unknown,
   không giả thành runtime lỗi. Local cũng tạm ngừng các task orchestration.
5. Stop qua Control Plane: Running null, health unknown, không probe tiếp theo.
6. Candidate readiness fail: giữ Running cũ; kiểm tra EN/VI, terminal kết thúc
   succeeded/failed/unconfirmed, không lifecycle healthy.

Không smoke gây gián đoạn trên runtime đang sử dụng.

## Validation

Pytest Control Plane/Model Server; Django check và makemigrations --check --dry-run
với settings test; Ruff; Web lint/build/test:health/test:workflow/test:metrics;
Compose config --quiet; Kustomize/Kubeconform; unittest discover k8s/validate/tests;
python -m k8s.validate.run_all; git diff --check. Mock tests không thay smoke
Celery/Redis/PostgreSQL thật. Không dùng settings production để validate offline.
