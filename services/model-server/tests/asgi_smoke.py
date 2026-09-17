import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            event = await receive()
            if event["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif event["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    else:
        await send({"type": "http.response.start", "status": 200})
        await send({"type": "http.response.body", "body": b"ready"})


def smoke(log_format="console", port=8050):
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "src.uvicorn_entrypoint",
            "asgi_smoke:app",
            "--service",
            "logging-smoke",
            "--port",
            str(port),
            "--workers",
            "2",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "LOG_FORMAT": log_format},
    )
    try:
        deadline = time.monotonic() + 15
        while True:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health", timeout=0.5
                ) as response:
                    assert response.read() == b"ready"
                break
            except (urllib.error.URLError, TimeoutError):
                if time.monotonic() >= deadline or process.poll() is not None:
                    raise AssertionError("Smoke server did not become ready")
                time.sleep(0.1)
    finally:
        process.send_signal(signal.SIGTERM)
        try:
            output, _ = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate()
            raise AssertionError("Smoke server did not stop")
    assert process.returncode == 0, output
    lines = [line for line in output.splitlines() if line]
    if log_format == "json":
        payloads = [json.loads(line) for line in lines]
        assert all(item["service"] == "logging-smoke" for item in payloads), output
    else:
        assert lines and all(" [INFO]: " in line for line in lines), output
    assert not any("GET /health" in line for line in lines), output
    print(
        f"Uvicorn smoke passed: {len(lines)} {log_format} lifecycle lines, no health access log"
    )


if __name__ == "__main__":
    smoke()
    smoke("json", 8051)
