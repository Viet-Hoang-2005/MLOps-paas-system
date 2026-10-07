"""Run inside the Linux runner image with isolated HTTP fixtures and no credentials."""

import base64
import io
import json
import os
import sys
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src.supervisor import run


stage = sys.argv[1]
reached = threading.Event()
archive = io.BytesIO()
train_code = "import os,pickle; from pathlib import Path; p=Path(os.environ['SM_MODEL_DIR']); p.mkdir(exist_ok=True); (p/'model.pkl').write_bytes(pickle.dumps({'model':'p1'}))\n"
if stage == "train":
    train_code += "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',\"import time; from pathlib import Path; p=Path('/tmp/p1-heartbeat');\\nwhile True: p.write_text(str(time.time())); time.sleep(.05)\"]); print('training-stage',flush=True); time.sleep(120)\n"
with zipfile.ZipFile(archive, "w") as source:
    source.writestr("train.py", train_code)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, body, content_type="application/octet-stream"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        slow = (stage == "download" and self.path == "/source") or (stage == "pip" and self.path.endswith(".whl"))
        if slow:
            reached.set()
            time.sleep(20)
        self.respond(archive.getvalue() if self.path == "/source" else b"feature,target\n1,0\n")

    def do_POST(self):
        self.respond(json.dumps({"upload_url": f"http://127.0.0.1:{server.server_port}/output"}).encode(), "application/json")

    def do_PUT(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        reached.set()
        if stage == "upload":
            time.sleep(20)
        self.respond(b"ok")


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
root = f"http://127.0.0.1:{server.server_port}"
os.environ.update(S3_SOURCE_URI=root + "/source", S3_TRAINING_DATA_URI=root + "/data", S3_OUTPUT_UPLOAD_URL=root + "/broker", S3_OUTPUT_UPLOAD_CAPABILITY="isolated-smoke", MAX_RUNTIME_SECONDS="8", TRAINING_JOB_ID="00000000-0000-0000-0000-000000000001")
if stage == "pip":
    os.environ["REQUIREMENTS_TEXT"] = base64.b64encode((root + "/p1fixture-0.0.1-py3-none-any.whl\n").encode()).decode()
started = time.monotonic()
code = run(timeout_seconds=15 if stage == "pip" else 8)
elapsed = time.monotonic() - started
assert code == (0 if stage == "success" else 124), (stage, code)
assert elapsed < 40, elapsed
if stage == "train":
    heartbeat = Path("/tmp/p1-heartbeat")
    assert heartbeat.exists(), "Training descendant did not start"
    value = heartbeat.read_text()
    time.sleep(.2)
    assert heartbeat.read_text() == value, "Descendant survived deadline"
else:
    assert reached.is_set(), f"Stage {stage} did not execute"
quota = Path("/sys/fs/cgroup/cpu.max").read_text().strip().split()
assert int(quota[0]) / int(quota[1]) == 2
assert int(Path("/sys/fs/cgroup/memory.max").read_text()) == 4096 * 1024 * 1024
print(f"PASS {stage}: exit={code}, elapsed={elapsed:.1f}s, CPU=2, RAM=4096MiB", flush=True)
