"""Enforce a wall-clock deadline around all runner stages and descendants."""

import os
import signal
import subprocess
import sys


def run(timeout_seconds=None, command=None):
    timeout = timeout_seconds or int(os.environ.get("MAX_RUNTIME_SECONDS", "3600"))
    child = subprocess.Popen(command or [sys.executable, "-u", "-m", "src.main", "--worker"], start_new_session=True)
    previous = signal.getsignal(signal.SIGTERM)

    def terminate(signum=None, frame=None):
        try:
            os.killpg(child.pid, signal.SIGTERM)
            child.wait(timeout=30)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            pass
        finally:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        child.wait()

    def interrupted(signum, frame):
        terminate()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, interrupted)
    try:
        try:
            return child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            print("[SYSTEM] Training execution deadline exceeded.", flush=True)
            terminate()
            return 124
    finally:
        signal.signal(signal.SIGTERM, previous)
