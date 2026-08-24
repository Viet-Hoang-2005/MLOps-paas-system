# Consumer

The consumer reads successful inference events from Redpanda and writes production observations to PostgreSQL.

- Parse and normalize event timestamps to UTC.
- Preserve nested feature/prediction JSON as JSONB; do not double encode.
- Group/count by model identity and read active drift thresholds.
- Empty, malformed, unknown-model, or unconfigured-threshold batches fail safely.
- Webhook failures are observable but do not corrupt committed data.
- Commit Kafka offsets only after durable database persistence succeeds.
- Flush on full batch, idle timeout, and final shutdown.

Tests use fake consumers, engines, frames, HTTP clients, and errors; never require a real broker or database.
