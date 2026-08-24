# Consumer — Production Data Ingestion Worker

Consumer là một **Background Worker** chạy liên tục, đóng vai trò trung gian giữa Event Stream (Redpanda Kafka) và Cơ sở dữ liệu dài hạn (PostgreSQL). Nó ghi signal automatic-drift vào transactional outbox cùng transaction với production data; một dispatcher thread riêng retry gửi signal tới Control Plane mà không chặn Kafka polling.

---

## Vai Trò

- **Kafka Consumer**: Lắng nghe liên tục topic `mlops_paas_production_data` từ Redpanda.
- **Micro-Batching**: Gom nhiều message vào buffer, chỉ `INSERT` vào PostgreSQL khi:
  - Đạt kích thước batch tối đa, **hoặc**
  - Vượt thời gian chờ idle (idle timeout).
- **Schema-Flexible Storage**: Lưu `features` dạng `JSONB` (hỗ trợ mọi số lượng features khác nhau giữa các mô hình), `prediction` dạng `TEXT`.
- **Transactional outbox**: Cùng transaction với mỗi batch INSERT, tạo một signal idempotent cho từng model version. Dispatcher thread trong mỗi Consumer replica lease signal, retry HTTP với exponential backoff và chỉ đánh dấu delivered sau phản hồi 2xx.
- **Control Plane owns drift state**: Control Plane kiểm tra threshold của `DriftMonitor`, lưu watermark trong PostgreSQL và tạo `DriftRun` idempotent. Consumer không truy cập bảng monitor hoặc giữ state trong memory.
- **At-Least-Once Delivery**: Batch được tách theo Kafka partition, giữ lại và pause partition khi PostgreSQL/offset commit lỗi. Offset cụ thể chỉ được commit sau PostgreSQL transaction thành công.
- **Idempotent Replay**: Event `id` là primary key; replay sau crash giữa DB commit và Kafka commit dùng `ON CONFLICT DO NOTHING`, nên không tạo duplicate.

---

## Luồng Hoạt Động

```
Redpanda (topic: mlops_paas_production_data)
  → Consumer subscribe, poll message
  → Gom buffer theo topic/partition (Micro-batching)
  → transaction INSERT production logs ... ON CONFLICT (id) DO NOTHING
      + INSERT automatic-drift signal ... ON CONFLICT (idempotency_key) DO NOTHING
      → PostgreSQL
  → commit(offset=message cuối + 1, synchronous)
  → chỉ xóa batch sau khi offset commit thành công

automatic-drift-outbox thread (inside Consumer)
  → lease pending signal → POST internal webhook → Control Plane
  → 2xx: mark published; lỗi: retry exponential backoff

Control Plane
  → lock active DriftMonitor → check durable row count and watermark
  → create idempotent DriftRun → Celery/Argo/Evidently
```

---

## Cấu Trúc Thư Mục

```
src/
├── main.py          # Kafka loop, dispatcher supervision and graceful shutdown
├── drift_outbox.py  # Lease and retry delivery of automatic-drift signals
└── database.py      # PostgreSQL persistence and outbox helpers
```

---

## Công nghệ

| Thành phần | Công nghệ |
|---|---|
| Message Broker | Redpanda (Kafka-compatible), `confluent-kafka` |
| Database | PostgreSQL + `psycopg2` / SQLAlchemy |
| Batch Processing | `pandas` DataFrame → `to_sql` bulk insert |

---

## Biến Môi Trường

| Biến | Mô tả |
|---|---|
| `REDPANDA_BROKERS` | Địa chỉ Redpanda broker (mặc định: `localhost:19092`) |
| `KAFKA_TOPIC` | Topic lắng nghe (mặc định: `mlops_paas_production_data`) |
| `KAFKA_BATCH_SIZE` | Số event tối đa trong một batch của một partition |
| `KAFKA_DB_RETRY_INITIAL_SECONDS` | Backoff retry PostgreSQL/offset commit ban đầu |
| `KAFKA_DB_RETRY_MAX_SECONDS` | Backoff retry tối đa; partition lỗi vẫn bị pause |
| `CONTROL_PLANE_AUTOMATIC_DRIFT_WEBHOOK_URL` | Internal Control Plane URL nhận automatic-drift signal |
| `CONTROL_PLANE_WEBHOOK_SECRET` | Secret header xác thực webhook |
| `AUTOMATIC_DRIFT_OUTBOX_POLL_SECONDS` | Chu kỳ poll outbox (mặc định: `5`) |
| `AUTOMATIC_DRIFT_OUTBOX_BATCH_SIZE` | Số signal claim mỗi vòng (mặc định: `50`) |
| `AUTOMATIC_DRIFT_OUTBOX_LEASE_SECONDS` | Thời gian lease để dispatcher ở replica khác không gửi trùng (mặc định: `60`) |
| `AUTOMATIC_DRIFT_OUTBOX_RETRY_INITIAL_SECONDS` | Backoff HTTP ban đầu (mặc định: `5`) |
| `AUTOMATIC_DRIFT_OUTBOX_RETRY_MAX_SECONDS` | Backoff HTTP tối đa (mặc định: `300`) |
| `AUTOMATIC_DRIFT_OUTBOX_REQUEST_TIMEOUT_SECONDS` | Timeout mỗi lần gọi Control Plane (mặc định: `10`) |
| `DB_USER`, `DB_PASSWORD`, `DB_HOST_RW`, `DB_PORT`, `DB_NAME` | PostgreSQL connection |

---

## Chạy Local

```bash
docker compose up control-plane consumer
```

Consumer sẽ tự động connect Redpanda và bắt đầu consume. Dispatcher thread chỉ gửi signal sau khi bản ghi và signal đã được commit PostgreSQL; nếu Control Plane chưa sẵn sàng, signal được giữ lại để retry. Nếu dispatcher chết ngoài dự kiến, Consumer thoát để Docker/Kubernetes restart toàn bộ process.
