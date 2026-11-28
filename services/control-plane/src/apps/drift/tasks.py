from apps.drift.monitors.tasks import cleanup_drift_monitor_task as cleanup_drift_monitor_task
from apps.drift.runs.tasks import cancel_drift_run as cancel_drift_run
from apps.drift.runs.tasks import execute_drift_run as execute_drift_run

# "skipped" is final: the run ended without a result because of too few samples.
TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled", "skipped"})
