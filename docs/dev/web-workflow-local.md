# Khởi chạy workflow mới trên Docker Compose

## Trạng thái và dữ liệu

Đã triển khai code cho năm giai đoạn trong [kế hoạch](web-workflow-refactor.md). Các test API/ORM dùng storage/execution giả lập; không thay thế smoke Docker/S3 thật.

Refactor sử dụng **clean bootstrap dữ liệu ứng dụng**: không có backfill Preview, snapshot hoặc active_deployment cho project cũ. Không dùng database cũ để nghiệm thu luồng mới. Không chạy `docker compose down -v`, không purge Celery và không xóa volume cũ để thử tính năng.

Compose có tên container cố định nên stack mới không thể chạy song song chỉ bằng đổi `--project-name`. Khi chuyển sang DB sạch, cần dừng client cũ trong cửa sổ local do bạn chủ động chọn; dữ liệu volume cũ vẫn giữ lại. Runtime động ngoài Compose phải được kiểm kê và dừng riêng nếu không còn dùng, không dùng lệnh xóa toàn Docker daemon.

## Khởi chạy do người dùng thực hiện

1. Sao lưu dữ liệu cần giữ; dừng nguồn sinh task và chờ các job đang chạy kết thúc. Giữ `.env` ngoài Git; không in nội dung của nó vào log.
2. Trong `.env`, đặt `POSTGRES_VOLUME_NAME=postgres_workflow_v2` (một tên volume **mới** chưa chứa dữ liệu). Giữ cấu hình AWS/S3, DB, JWT và credentials hợp lệ theo `.env.example`. Không thay đổi backend sang Argo khi chạy local. `TRAINING_ENABLED` phải được bật nếu muốn thử training local.
3. Dừng client rồi tạo lại stack bằng code mới:

   ```bash
   docker compose stop control-plane celery-worker consumer model-server
   docker compose build model-packager training-runner evidently machine-learning-serving deep-learning-serving
   docker compose up -d --build postgres schema-init redis redpanda redpanda-init mlflow control-plane celery-worker model-server consumer traefik prometheus cadvisor
   docker compose config --quiet
   docker compose logs --tail 80 control-plane celery-worker
   ```

   PostgreSQL giữ volume cũ, mount volume mới theo tên đã chọn. Control Plane chạy migration khi khởi động. MLflow/cache/broker có volume riêng; đây không phải reset tự động toàn bộ hệ thống. Đảm bảo không còn task cũ trong broker trước khi khởi động worker trên database mới; nếu còn, dùng stack/broker riêng hoặc xử lý từng task có xác nhận, không purge tùy tiện.

4. Chạy Web:

   ```bash
   cd web
   pnpm install --frozen-lockfile
   pnpm dev
   ```

5. Tạo tài khoản local qua giao diện hoặc `docker compose exec control-plane python manage.py createsuperuser`. Kiểm tra `/health/live` và `/health/ready` trên Control Plane (`localhost:8000`). Gateway Model Server được publish ở `localhost:5001`, cổng container là `5000`.

## Luồng và API

| Thao tác | Contract |
| --- | --- |
| New project | `POST /api/models/` multipart; bắt buộc artifact, optional `.py`, `.csv`, Advanced artifacts |
| New project từ Training | `POST /api/models/training-projects/`; chưa cần artifact |
| Đọc/sửa Preview | `GET/PATCH /api/models/<project>/preview/`; PATCH phải có revision hiện tại |
| Build Preview | `POST /api/models/<project>/builds/` với revision |
| Build trained model | `POST /api/training-jobs/<job>/build/`; chỉ nhận output completed hợp lệ |
| Register | `POST /api/builds/<build>/register/`; async, idempotent, không tự deploy |
| Deploy | `POST /api/deployments/` với Build đã đăng ký; theo dõi deployment UUID |
| Snapshot source | `GET /api/models/<project>/running-source/` chỉ đọc version Running |
| Drift monitor | `POST /api/drift-monitors/`; chỉ version Running, CSV riêng nếu version không có reference |
| Training retry | `POST /api/training-jobs/<job>/retry/`; tạo job mới từ input bất biến, không đọc workspace hiện tại |
| Metric | `GET /api/observability/models/<project>/runtime-metrics/?window=1h`; window `15m/1h/24h` |
| Delete project | `DELETE /api/models/<project>/`; async hard cleanup, lỗi giữ `delete_failed` để retry |

Các route Web bắt đầu ở `/dashboard/projects`. Trang chính theo `/dashboard/projects/<project>/{overview,deployment,monitoring,training,evolution}`. Form tạo deployment và monitoring có selector riêng; Header chọn project ở trang chi tiết sẽ về Overview. API Token ở `/dashboard/api-tokens`, không còn nằm trong Settings.

Preview thay đổi không ảnh hưởng snapshot đang Running. Build thành công chỉ bật Register; Register xong mới mở bước Deploy. Deployment mới chỉ trở thành Running sau readiness; lỗi không thay bản đang phục vụ. Khi chuyển Running, monitor cũ ngừng auto-trigger và giữ lịch sử; tạo monitor mới thủ công.

## Quan sát local

- Prometheus + cAdvisor chạy nội bộ, không publish port. Retention 7 ngày, scrape 15 giây.
- Scrape gateway tại `model-server:5000`, API tại `control-plane:8000/health/metrics`, cAdvisor tại `cadvisor:8080`.
- CPU cores/RAM MiB lọc theo label runtime deployment/tenant; RPS theo counter gateway project/version. Không gửi PromQL tùy ý từ Web.
- UI báo `no_data` hoặc `unavailable` nếu chưa có mẫu/nguồn lỗi; không coi số 0 là phép đo thành công.
- cAdvisor cần quyền/mount host để đọc Docker metric. Docker Desktop/WSL có thể không cung cấp đủ metric; kiểm tra target UP và label thực tế trước khi kết luận biểu đồ đúng. Không nới quyền hoặc mở port công khai để xử lý.
- Log dùng Redis; trạng thái job và Running lấy từ PostgreSQL, không suy luận từ nội dung TerminalViewer.

## Kiểm thử nghiệm thu còn phải chạy trên runtime thật

1. Raw model + label mapping → Build → Register → Deploy → predict đúng nhãn.
2. MLflow ZIP và requirements thực tế được giữ trong snapshot Evolution.
3. Sửa Preview trong lúc Running: Code/Data vẫn là snapshot cũ; deploy bản mới thành công mới chuyển.
4. Training project chưa artifact → Set as Reference → training → Build → Register → Deploy; đổi/xóa workspace không làm đổi input retry.
5. Deployment lỗi: runtime cũ còn phục vụ; registration/cleanup lỗi có thể retry.
6. Drift dùng reference của version hoặc CSV riêng → Evidently hoàn tất → report mở được; lịch sử version cũ còn nguyên.
7. CPU/RAM/RPS có mẫu thật, không lẫn deployment; mất Prometheus hiển thị unavailable.
8. Hard delete chỉ dọn runtime/job/image/object/cache/DB của project chọn; project khác không bị ảnh hưởng.
9. F5/deep link/Header/dirty form; light/dark, keyboard và mobile/tablet/desktop.

Đối với Argo production sau này, adapter và Sensor đã đổi runtime theo deployment UUID. Xóa project đang có Argo workflow hoạt động phải xác nhận workflow đã dừng; cleanup fail closed nếu backend không xác nhận được cancel. Không triển khai cluster trong đợt local này.

## Test tự động

```bash
# services/control-plane
python -m pytest
python manage.py check --settings=config.settings.test
python manage.py makemigrations --check --dry-run --settings=config.settings.test
# services/model-server; logging test sử dụng môi trường local
LOG_FORMAT=console python -m pytest
# web
pnpm lint
pnpm build
pnpm test:workflow
# root
docker compose config --quiet
git diff --check
```

Không áp dụng migration vào DB cũ rồi giả định dữ liệu cũ đã được backfill. Muốn hỗ trợ dữ liệu cũ cần một kế hoạch migration riêng, ngoài phạm vi clean refactor này.
