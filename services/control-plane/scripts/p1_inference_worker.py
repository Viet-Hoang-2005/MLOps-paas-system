"""Small deterministic serving fixture for gateway/browser acceptance."""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.reply({"status": "healthy", "project_id": os.environ["PROJECT_ID"], "model_version_id": os.environ["MODEL_VERSION_ID"]})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.reply({"prediction": [1], "confidence": 1.0, "engine": "ml"})

    def reply(self, data):
        payload = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


HTTPServer(("0.0.0.0", 5001), Handler).serve_forever()
