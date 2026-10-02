# Consumer

The Consumer (`services/consumer/`) is a high-throughput background worker executing between Redpanda Kafka and PostgreSQL.

## Core Responsibilities

1. **Kafka Telemetry Ingestion:** Continuously subscribes to topic `mlops_paas_production_data`.
2. **Micro-Batching:** Accumulates records per Kafka partition and bulk-inserts into PostgreSQL when reaching `KAFKA_BATCH_SIZE` or exceeding idle timeout.
3. **Schema Ownership & Zero DDL:** Consumer never executes DDL (`CREATE TABLE`). It expects Control Plane migrations to create `control_plane.production_predictionrecord` and `control_plane.observability_eventoutbox`.
4. **Flexible Storage:** Parses UTC timestamps, flattens/validates payload, and persists nested features as `JSONB` with prediction results as `TEXT`.
5. **Transactional Outbox for Automatic Drift:** In the exact same database transaction as the production record insert, inserts a deterministic signal into `control_plane.observability_eventoutbox`.
6. **Non-Blocking Dispatcher Thread:** A dedicated background thread (`automatic-drift-outbox`) leases pending outbox signals (`lease_seconds=60`) and dispatches HTTP POST requests to `CONTROL_PLANE_AUTOMATIC_DRIFT_WEBHOOK_URL` with exponential backoff. Network or Control Plane latency never blocks the main Kafka polling loop.
7. **At-Least-Once Delivery & Idempotent Replay:**
   - Synchronously commits Kafka offsets (`consumer.commit(asynchronous=False)`) ONLY AFTER the PostgreSQL transaction succeeds.
   - Bulk inserts use `ON CONFLICT (id) DO NOTHING` to eliminate duplicates during replay after crashes.
8. **Partition-Level Error Isolation:** If a database error or offset commit fails, Consumer pauses only the affected partition and applies backoff retries (`KAFKA_DB_RETRY_INITIAL_SECONDS` to `KAFKA_DB_RETRY_MAX_SECONDS`); unaffected partitions continue processing.
