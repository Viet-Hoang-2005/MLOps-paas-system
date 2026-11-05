import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("deployment,training,drift", [
    (False, False, False),
    (True, False, False),
    (False, True, False),
    (False, False, True),
    (True, True, True),
])
def test_watch_settings_and_schedules_are_independent(deployment, training, drift):
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(Path(__file__).resolve().parents[3]),
        "EXECUTION_BACKEND": "docker",
        "TRAINING_BACKEND": "docker",
        "TRAINING_MAX_RUNTIME_SECONDS": "86400",
        "LOCAL_DEPLOYMENT_WATCH_ENABLED": str(deployment),
        "TRAINING_EXECUTION_WATCH_ENABLED": str(training),
        "DRIFT_EXECUTION_WATCH_ENABLED": str(drift),
        # Old variables must never activate a watcher.
        "LOCAL_EXECUTION_WATCH_ENABLED": "true",
        "EXECUTION_WATCH_ENABLED": "true",
    })
    script = (
        "import json; from config.settings import base; "
        "print(json.dumps({'deployment': base.LOCAL_DEPLOYMENT_WATCH_ENABLED, "
        "'training': base.TRAINING_EXECUTION_WATCH_ENABLED, 'drift': base.DRIFT_EXECUTION_WATCH_ENABLED, "
        "'deployment_scan': 'local-execution-scan' in base.CELERY_BEAT_SCHEDULE, "
        "'job_scan': 'job-execution-scan' in base.CELERY_BEAT_SCHEDULE}))"
    )
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, check=True)
    values = json.loads(result.stdout)
    assert values == {"deployment": deployment, "training": training, "drift": drift,
                      "deployment_scan": deployment, "job_scan": training or drift}
