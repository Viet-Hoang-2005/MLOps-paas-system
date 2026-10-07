import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.supervisor import run


pytestmark = pytest.mark.skipif(os.name != "posix", reason="Runner process groups require Linux.")


def test_supervisor_propagates_exit_code():
    assert run(timeout_seconds=5, command=[sys.executable, "-c", "raise SystemExit(7)"]) == 7


def test_deadline_kills_nested_subprocess(tmp_path):
    heartbeat = tmp_path / "heartbeat"
    descendant = "import time; from pathlib import Path; p=Path(" + repr(str(heartbeat)) + ");\nwhile True: p.write_text(str(time.time())); time.sleep(.05)"
    parent = "import subprocess, sys, time; subprocess.Popen([sys.executable,'-c'," + repr(descendant) + "]); time.sleep(120)"
    assert run(timeout_seconds=1, command=[sys.executable, "-c", parent]) == 124
    assert heartbeat.exists()
    last = heartbeat.read_text()
    time.sleep(.2)
    assert heartbeat.read_text() == last


def test_external_sigterm_stops_runner_group(tmp_path):
    marker = tmp_path / "terminated"
    child = "import signal,time; from pathlib import Path; signal.signal(signal.SIGTERM,lambda *a: (Path(" + repr(str(marker)) + ").write_text('terminated'),exit(0))); print('ready',flush=True); time.sleep(120)"
    parent = "from src.supervisor import run; import sys; sys.exit(run(timeout_seconds=120,command=[sys.executable,'-c'," + repr(child) + "]))"
    process = subprocess.Popen([sys.executable, "-c", parent], stdout=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == "ready"
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5) == 143
        assert marker.read_text() == "terminated"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_deadline_escalates_to_sigkill_after_grace():
    child = "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(120)"
    started = time.monotonic()
    assert run(timeout_seconds=1, command=[sys.executable, "-c", child]) == 124
    assert 30 <= time.monotonic() - started < 35
