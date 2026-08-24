"""Generate the Control Plane's local application secrets in the project .env.

The script preserves unrelated variables, writes the file atomically, and never
prints generated secret values. Existing non-empty secrets are kept unless
``--force`` is supplied explicitly.

Usage::

    python scripts/generate_control_plane_secrets.py
    python scripts/generate_control_plane_secrets.py --force

Use ``--force`` only for intentional rotation. It replaces all five secrets and
therefore invalidates JWTs signed by the previous key pair.
"""

from __future__ import annotations

import argparse
import os
import secrets
import stat
import sys
import tempfile
from pathlib import Path

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
except ImportError as exc:  # pragma: no cover - depends on the caller environment
    raise SystemExit(
        "Missing dependency 'cryptography'. Install the Control Plane requirements "
        "before running this script."
    ) from exc


SECRET_KEYS = (
    "DJANGO_SECRET_KEY",
    "JWT_PRIVATE_KEY",
    "JWT_PUBLIC_KEY",
    "CONTROL_PLANE_WEBHOOK_SECRET",
    "ARGO_EVENTS_WEBHOOK_TOKEN",
)


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Generate Control Plane secrets and store them in a local .env file."
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=project_root / ".env",
        help="Target dotenv file (default: the repository root .env).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rotate and replace existing non-empty Control Plane secrets.",
    )
    return parser.parse_args()


def generate_jwt_key_pair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return private_pem, public_pem


def dotenv_value(value: str) -> str:
    """Encode a value as one double-quoted dotenv line without real newlines."""
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )
    return f'"{escaped}"'


def assignment_key(line: str) -> str | None:
    candidate = line.lstrip()
    if not candidate or candidate.startswith("#") or "=" not in candidate:
        return None
    key = candidate.split("=", 1)[0].strip()
    if key.startswith("export "):
        key = key.removeprefix("export ").strip()
    return key or None


def has_non_empty_assignment(line: str) -> bool:
    if "=" not in line:
        return False
    raw_value = line.split("=", 1)[1].strip()
    return raw_value not in {"", "''", '""'}


def existing_non_empty_keys(content: str) -> set[str]:
    keys: set[str] = set()
    for line in content.splitlines():
        key = assignment_key(line)
        if key in SECRET_KEYS and has_non_empty_assignment(line):
            keys.add(key)
    return keys


def update_env_content(
    original: str,
    generated: dict[str, str],
    *,
    force: bool,
) -> tuple[str, list[str], list[str]]:
    lines = original.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in original else "\n"
    replaced: set[str] = set()
    preserved: set[str] = set()
    output: list[str] = []

    for line in lines:
        key = assignment_key(line)
        if key not in generated:
            output.append(line)
            continue

        if key in replaced or key in preserved:
            # Drop duplicate definitions for a secret that this script owns.
            continue

        if has_non_empty_assignment(line) and not force:
            output.append(line)
            preserved.add(key)
            continue

        output.append(f"{key}={dotenv_value(generated[key])}{newline}")
        replaced.add(key)

    missing = [key for key in SECRET_KEYS if key not in replaced | preserved]
    if missing:
        if output and not output[-1].endswith(("\n", "\r")):
            output[-1] += newline
        if output and output[-1].strip():
            output.append(newline)
        output.append(f"# Control Plane application secrets{newline}")
        for key in missing:
            output.append(f"{key}={dotenv_value(generated[key])}{newline}")
            replaced.add(key)

    return "".join(output), sorted(replaced), sorted(preserved)


def write_atomically(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
            # Windows ACLs are not represented fully by POSIX mode bits.
            pass
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def main() -> int:
    args = parse_args()
    env_path = args.env_file.expanduser().resolve()
    original = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    existing_keys = existing_non_empty_keys(original)
    jwt_keys = {"JWT_PRIVATE_KEY", "JWT_PUBLIC_KEY"}
    if not args.force and existing_keys & jwt_keys and not jwt_keys <= existing_keys:
        print(
            "Refusing to generate only one JWT key because that would create a "
            "mismatched signing pair. Re-run with --force to rotate both keys.",
            file=sys.stderr,
        )
        return 2

    private_key, public_key = generate_jwt_key_pair()
    generated = {
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
        "JWT_PRIVATE_KEY": private_key,
        "JWT_PUBLIC_KEY": public_key,
        "CONTROL_PLANE_WEBHOOK_SECRET": secrets.token_urlsafe(48),
        "ARGO_EVENTS_WEBHOOK_TOKEN": secrets.token_urlsafe(48),
    }
    updated, written, preserved = update_env_content(
        original,
        generated,
        force=args.force,
    )

    if not written:
        print(
            "No changes were made. All Control Plane secrets already exist; "
            "use --force only when intentional rotation is required."
        )
        return 0

    write_atomically(env_path, updated)
    print(f"Updated {len(written)} Control Plane secret(s) in {env_path}.")
    print("Updated keys: " + ", ".join(written))
    if preserved:
        print("Preserved existing keys: " + ", ".join(preserved))
    if args.force:
        print("JWT signing keys were rotated; existing access tokens are now invalid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
