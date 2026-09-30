"""Prepare local secrets and publish selected groups to Terraform-owned AWS containers.

Only the five Control Plane secrets are generated. Other credentials must be
obtained from their respective providers and entered in .env by the operator.
Secret values, PEM keys and AWS payloads are never printed.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import secrets
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTROL_PLANE_GROUP = 5
JWT_KEYS = ("JWT_PRIVATE_KEY", "JWT_PUBLIC_KEY")
GENERATED_KEYS = (
    "DJANGO_SECRET_KEY",
    *JWT_KEYS,
    "CONTROL_PLANE_WEBHOOK_SECRET",
    "ARGO_EVENTS_WEBHOOK_TOKEN",
)
ROTATION_KEYS = {
    "django": ("DJANGO_SECRET_KEY",),
    "jwt": JWT_KEYS,
    "control-plane-webhook": ("CONTROL_PLANE_WEBHOOK_SECRET",),
    "argo-events-webhook": ("ARGO_EVENTS_WEBHOOK_TOKEN",),
}
ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=")

SECRET_GROUPS: dict[int, dict[str, Any]] = {
    1: {
        "name": "Database Secrets (PostgreSQL)",
        "target": "mlops/production-secrets",
        "keys": ["DB_USER", "DB_PASSWORD"],
    },
    2: {
        "name": "Redis Secrets",
        "target": "mlops/production-secrets",
        "keys": ["REDIS_PASSWORD", "REDIS_SENTINEL_PASSWORD"],
    },
    3: {
        "name": "Harbor Registry Secrets",
        "target": "mlops/production-secrets",
        "keys": ["HARBOR_USERNAME", "HARBOR_PASSWORD"],
    },
    4: {
        "name": "Cloudflare Tunnel Secret",
        "target": "mlops/production-secrets",
        "keys": ["TUNNEL_TOKEN"],
    },
    5: {
        "name": "Control Plane & Auth Secrets",
        "target": "mlops/production-secrets",
        "keys": list(GENERATED_KEYS),
    },
    6: {
        "name": "OAuth Credentials",
        "target": "mlops/production-secrets",
        "keys": [
            "GOOGLE_OAUTH2_CLIENT_ID",
            "GITHUB_OAUTH2_CLIENT_ID",
            "GITHUB_OAUTH2_CLIENT_SECRET",
        ],
    },
    7: {
        "name": "Email SMTP Credentials",
        "target": "mlops/production-secrets",
        "keys": ["EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD"],
    },
    8: {
        "name": "GitHub Cluster Secrets",
        "target": "mlops/production-secrets",
        "keys": ["GITHUB_TOKEN", "GITHUB_REPO"],
    },
    9: {
        "name": "GitHub Actions CI/CD Secrets",
        "target": "mlops/github-actions-secrets",
        "keys": [
            "GITHUB_REPO",
            "GITHUB_TOKEN",
            "HARBOR_GITHUB_USERNAME",
            "HARBOR_GITHUB_PASSWORD",
        ],
    },
    10: {
        "name": "AWS IAM Credentials",
        "target": "mlops/aws-secrets",
        "keys": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
    },
}


class SecretPreparationError(Exception):
    """Safe, value-free error intended for operator output."""


def parse_groups(raw: str) -> list[int]:
    parts = raw.replace(",", " ").split()
    if not parts:
        raise SecretPreparationError("Select at least one secret group.")
    if "0" in parts:
        if len(parts) != 1:
            raise SecretPreparationError(
                "Group 0 (all) cannot be combined with other groups."
            )
        return list(SECRET_GROUPS)
    if any(not part.isdigit() or int(part) not in SECRET_GROUPS for part in parts):
        raise SecretPreparationError(
            "Invalid group selection; choose 0 or group numbers 1-10."
        )
    return sorted({int(part) for part in parts})


def select_groups(cli_groups: str | None) -> list[int]:
    if cli_groups is not None:
        return parse_groups(cli_groups)
    print("Secret groups (0 = all):")
    for number, group in SECRET_GROUPS.items():
        print(f"  {number:2d}: {group['name']}")
    try:
        return parse_groups(input("Select groups (e.g. 5 or 1,2): ").strip())
    except EOFError as exc:
        raise SecretPreparationError("No group selection received.") from exc


def parse_env_content(content: str) -> dict[str, str]:
    parsed = dotenv_values(stream=io.StringIO(content))
    return {key: value for key, value in parsed.items() if value is not None}


def quoted_dotenv(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )
    return f'"{escaped}"'


def update_env_content(
    original: str, replacements: dict[str, str], managed_keys: set[str]
) -> str:
    """Keep unrelated text and the final effective assignment of each managed key."""
    newline = "\r\n" if "\r\n" in original else "\n"
    lines = original.splitlines(keepends=True)
    last_index: dict[str, int] = {}
    for index, line in enumerate(lines):
        match = ASSIGNMENT.match(line)
        if match and match.group(1) in managed_keys:
            last_index[match.group(1)] = index

    output: list[str] = []
    for index, line in enumerate(lines):
        match = ASSIGNMENT.match(line)
        key = match.group(1) if match else None
        if key not in managed_keys:
            output.append(line)
        elif last_index[key] == index:
            output.append(
                f"{key}={quoted_dotenv(replacements[key])}{newline}"
                if key in replacements
                else line
            )

    missing = [key for key in replacements if key not in last_index]
    if missing:
        if output and not output[-1].endswith(("\r", "\n")):
            output.append(newline)
        for key in missing:
            output.append(f"{key}={quoted_dotenv(replacements[key])}{newline}")
    return "".join(output)


def generate_jwt_key_pair() -> tuple[str, str]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = (
        private.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    return private_pem, public_pem


def validate_jwt_key_pair(private_pem: str, public_pem: str) -> None:
    try:
        private = serialization.load_pem_private_key(
            private_pem.encode(), password=None
        )
        public = serialization.load_pem_public_key(public_pem.encode())
        if private.public_key().public_numbers() != public.public_numbers():
            raise ValueError("mismatched key pair")
    except (TypeError, ValueError, AttributeError) as exc:
        raise SecretPreparationError(
            "Existing JWT keys are invalid or mismatched; use --rotate jwt to replace both."
        ) from exc


def prepare_env_content(
    original: str, selected_groups: list[int], rotate: list[str]
) -> tuple[str, dict[str, str]]:
    if rotate and CONTROL_PLANE_GROUP not in selected_groups:
        raise SecretPreparationError(
            "Rotation requires selecting Control Plane group 5."
        )
    selected_keys = {
        key for group_id in selected_groups for key in SECRET_GROUPS[group_id]["keys"]
    }
    values = parse_env_content(original)
    replacements: dict[str, str] = {}
    if CONTROL_PLANE_GROUP in selected_groups:
        rotated = {key for name in rotate for key in ROTATION_KEYS[name]}
        private_present = bool(values.get(JWT_KEYS[0], "").strip())
        public_present = bool(values.get(JWT_KEYS[1], "").strip())
        if private_present != public_present and "jwt" not in rotate:
            raise SecretPreparationError(
                "JWT key pair is incomplete; use --rotate jwt to replace both keys."
            )
        if "jwt" in rotate or not private_present:
            replacements[JWT_KEYS[0]], replacements[JWT_KEYS[1]] = (
                generate_jwt_key_pair()
            )
        else:
            validate_jwt_key_pair(values[JWT_KEYS[0]], values[JWT_KEYS[1]])
        for key, size in (
            ("DJANGO_SECRET_KEY", 64),
            ("CONTROL_PLANE_WEBHOOK_SECRET", 48),
            ("ARGO_EVENTS_WEBHOOK_TOKEN", 48),
        ):
            if key in rotated or not values.get(key, "").strip():
                replacements[key] = secrets.token_urlsafe(size)

    updated = update_env_content(original, replacements, selected_keys)
    effective = parse_env_content(updated)
    missing = sorted(key for key in selected_keys if not effective.get(key, "").strip())
    if missing:
        raise SecretPreparationError(
            "Selected groups have missing .env values: " + ", ".join(missing)
        )
    if CONTROL_PLANE_GROUP in selected_groups:
        argo_token = effective["ARGO_EVENTS_WEBHOOK_TOKEN"]
        callback_secret = effective["CONTROL_PLANE_WEBHOOK_SECRET"]
        if len(argo_token) < 32 or argo_token == callback_secret:
            raise SecretPreparationError(
                "ARGO_EVENTS_WEBHOOK_TOKEN must be at least 32 characters and differ from CONTROL_PLANE_WEBHOOK_SECRET."
            )
    return updated, effective


def write_atomically(path: Path, content: str) -> None:
    previous_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.chmod(previous_mode)
        os.replace(temporary_path, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass  # Windows ACLs are not fully represented by POSIX modes.
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def make_payloads(env: dict[str, str], groups: list[int]) -> dict[str, dict[str, str]]:
    payloads: dict[str, dict[str, str]] = {}
    for group_id in groups:
        group = SECRET_GROUPS[group_id]
        target = payloads.setdefault(group["target"], {})
        for key in group["keys"]:
            target[key] = env[key]
    return payloads


def get_existing_payload(client: Any, target: str) -> dict[str, Any]:
    """Distinguish a Terraform-owned empty container from a missing container."""
    try:
        client.describe_secret(SecretId=target)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
            raise SecretPreparationError(
                f"AWS container {target} is missing; run Terraform first."
            ) from None
        raise
    try:
        response = client.get_secret_value(SecretId=target)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
            return {}  # Metadata exists but no AWSCURRENT version has been published.
        raise
    secret_string = response.get("SecretString")
    if secret_string is None:
        raise SecretPreparationError(
            f"AWS container {target} does not contain a JSON SecretString."
        )
    try:
        existing = json.loads(secret_string)
    except json.JSONDecodeError as exc:
        raise SecretPreparationError(
            f"AWS container {target} contains invalid JSON; refusing overwrite."
        ) from exc
    if not isinstance(existing, dict):
        raise SecretPreparationError(
            f"AWS container {target} must contain a JSON object."
        )
    return existing


def confirm(
    groups: list[int], changes: dict[str, list[str]], env_changed: bool
) -> bool:
    print("Selected groups: " + ", ".join(str(group_id) for group_id in groups))
    print("Local .env: " + ("create/update" if env_changed else "unchanged"))
    for target, keys in changes.items():
        print(f"AWS {target}: " + (", ".join(keys) if keys else "unchanged"))
    try:
        return input(
            "Write .env and publish changed keys? [y/yes]: "
        ).strip().lower() in {"y", "yes"}
    except EOFError:
        return False


def publish(
    *,
    env_path: Path,
    example_path: Path,
    groups: list[int],
    rotate: list[str],
    yes: bool,
    client: Any | None = None,
) -> int:
    if env_path.exists():
        original = env_path.read_text(encoding="utf-8")
    elif example_path.exists():
        original = example_path.read_text(encoding="utf-8")
    else:
        raise SecretPreparationError(".env and .env.example are both missing.")
    updated, values = prepare_env_content(original, groups, rotate)
    payloads = make_payloads(values, groups)
    if client is None:
        region = (
            values.get("AWS_DEFAULT_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or "ap-southeast-1"
        )
        client_kwargs: dict[str, str] = {"region_name": region}
        access_key = values.get("AWS_ACCESS_KEY_ID") or os.environ.get(
            "AWS_ACCESS_KEY_ID"
        )
        secret_key = values.get("AWS_SECRET_ACCESS_KEY") or os.environ.get(
            "AWS_SECRET_ACCESS_KEY"
        )
        if access_key and secret_key:
            client_kwargs.update(
                aws_access_key_id=access_key, aws_secret_access_key=secret_key
            )
        client = boto3.client("secretsmanager", **client_kwargs)

    merged: dict[str, dict[str, Any]] = {}
    changes: dict[str, list[str]] = {}
    for target, payload in payloads.items():
        existing = get_existing_payload(client, target)
        merged[target] = {**existing, **payload}
        changes[target] = sorted(
            key for key, value in payload.items() if existing.get(key) != value
        )

    env_changed = not env_path.exists() or updated != original
    if not yes and not confirm(groups, changes, env_changed):
        print("Cancelled; no local or AWS changes made.")
        return 0
    if env_changed:
        write_atomically(env_path, updated)
        print(f"Updated local {env_path.name}.")
    for target, keys in changes.items():
        if not keys:
            print(f"Unchanged: {target}.")
            continue
        client.put_secret_value(
            SecretId=target, SecretString=json.dumps(merged[target], ensure_ascii=False)
        )
        print(f"Published {target}: {', '.join(keys)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--groups", help="Group numbers, comma separated; 0 selects all."
    )
    parser.add_argument(
        "--rotate",
        action="append",
        choices=tuple(ROTATION_KEYS),
        default=[],
        help="Rotate one generated secret group; repeatable.",
    )
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Confirm local and AWS writes without prompting.",
    )
    args = parser.parse_args(argv)
    try:
        groups = select_groups(args.groups)
        return publish(
            env_path=args.env_file.expanduser().resolve(),
            example_path=PROJECT_ROOT / ".env.example",
            groups=groups,
            rotate=args.rotate,
            yes=args.yes,
        )
    except SecretPreparationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "UnknownAWSFailure")
        print(
            f"AWS request failed ({code}); .env is retained for a safe retry.",
            file=sys.stderr,
        )
    except (BotoCoreError, OSError) as exc:
        print(
            f"{type(exc).__name__}; .env is retained for a safe retry.", file=sys.stderr
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
