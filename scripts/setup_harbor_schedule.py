#!/usr/bin/env python3
"""
Script thiết lập lịch Garbage Collection (GC) tự động cho Harbor Registry bằng Python.
Nạp biến môi trường từ hệ thống hoặc file .env (HARBOR_ADMIN_USERNAME, HARBOR_ADMIN_PASSWORD).
"""

import base64
import json
import os
import ssl
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def load_env_file():
    """Tự động tìm và nạp các biến môi trường từ file .env ở thư mục gốc repo."""
    current = Path(__file__).resolve()
    for parent in [current.parent, current.parent.parent, current.parent.parent.parent]:
        env_file = parent / ".env"
        if env_file.is_file():
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        if key not in os.environ:
                            os.environ[key] = val
            break


def main():
    load_env_file()

    harbor_user = os.environ.get("HARBOR_ADMIN_USERNAME", "admin")
    harbor_pass = os.environ.get("HARBOR_ADMIN_PASSWORD")
    harbor_url = os.environ.get(
        "HARBOR_REGISTRY_URL", "registry.mlops-nids-nt114.id.vn"
    )

    if not harbor_url.startswith("http://") and not harbor_url.startswith("https://"):
        harbor_url = f"https://{harbor_url}"
    harbor_url = harbor_url.rstrip("/")

    if not harbor_pass:
        print(
            "Error: Please set the HARBOR_ADMIN_PASSWORD environment variable.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(
        f"Setting up daily Garbage Collection schedule (00:00 AM) for Harbor at: {harbor_url}"
    )
    endpoint = f"{harbor_url}/api/v2.0/system/gc/schedule"

    payload = {
        "schedule": {"type": "Daily", "cron": "0 0 0 * * *"},
        "parameters": {"delete_untagged": True},
    }
    data = json.dumps(payload).encode("utf-8")

    auth_raw = f"{harbor_user}:{harbor_pass}".encode()
    auth_b64 = base64.b64encode(auth_raw).decode("ascii")

    headers = {"Content-Type": "application/json", "Authorization": f"Basic {auth_b64}"}

    req = Request(endpoint, data=data, headers=headers, method="POST")

    # Bỏ qua xác thực SSL trong môi trường nội bộ/self-signed nếu cần
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with urlopen(req, context=ctx) as resp:
            print(f"Successfully set up! HTTP Code: {resp.status}")
    except HTTPError as e:
        print(
            f"HTTP Error from Harbor ({e.code}): {e.read().decode('utf-8', errors='ignore')}",
            file=sys.stderr,
        )
        sys.exit(1)
    except URLError as e:
        print(f"Error connecting to Harbor: {e.reason}", file=sys.stderr)
        sys.exit(1)

    # Truy vấn lại thông tin lịch hiện tại
    print("Current Garbage Collection schedule on the system:")
    req_get = Request(
        endpoint, headers={"Authorization": f"Basic {auth_b64}"}, method="GET"
    )
    try:
        with urlopen(req_get, context=ctx) as resp:
            schedule_info = json.loads(resp.read().decode("utf-8"))
            print(json.dumps(schedule_info, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error reading GC schedule: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
