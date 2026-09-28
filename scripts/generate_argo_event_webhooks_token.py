"""Generate ARGO_EVENTS_WEBHOOK_TOKEN in the project .env.

The token authenticates the Control Plane (API and Celery) against the Argo
Events webhook EventSource. The script preserves unrelated variables, writes the
file atomically and never prints the token. An existing non-empty token is kept
unless ``--force`` is supplied.

Usage::

    python scripts/generate_argo_event_webhooks_token.py
    python scripts/generate_argo_event_webhooks_token.py --force

Afterwards publish it with ``python scripts/push_secrets_to_aws.py``.
"""

from __future__ import annotations

import argparse
import os
import secrets
import stat
import sys
import tempfile
from pathlib import Path

TOKEN_KEY = "ARGO_EVENTS_WEBHOOK_TOKEN"


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description=f"Generate {TOKEN_KEY} and store it in a local .env file."
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
        help="Rotate the token even if a non-empty value already exists.",
    )
    return parser.parse_args()


def assignment_key(line: str) -> str | None:
    candidate = line.lstrip()
    if not candidate or candidate.startswith("#") or "=" not in candidate:
        return None
    key = candidate.split("=", 1)[0].strip()
    if key.startswith("export "):
        key = key.removeprefix("export ").strip()
    return key or None


def has_non_empty_assignment(line: str) -> bool:
    raw_value = line.split("=", 1)[1].strip()
    return raw_value not in {"", "''", '""'}


def update_env_content(original: str, token: str, *, force: bool) -> tuple[str, bool]:
    """Return the new content and whether the token was written."""
    newline = "\r\n" if "\r\n" in original else "\n"
    output: list[str] = []
    seen = False
    written = False

    for line in original.splitlines(keepends=True):
        if assignment_key(line) != TOKEN_KEY:
            output.append(line)
            continue
        if seen:
            # Drop duplicate definitions so the effective value is unambiguous.
            continue
        seen = True
        if has_non_empty_assignment(line) and not force:
            output.append(line)
            continue
        output.append(f'{TOKEN_KEY}="{token}"{newline}')
        written = True

    if not seen:
        if output and not output[-1].endswith(("\n", "\r")):
            output[-1] += newline
        output.append(f'{TOKEN_KEY}="{token}"{newline}')
        written = True

    return "".join(output), written


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

    # token_urlsafe only emits [A-Za-z0-9_-], so no dotenv escaping is needed.
    updated, written = update_env_content(
        original, secrets.token_urlsafe(48), force=args.force
    )
    if not written:
        print(
            f"No changes were made. {TOKEN_KEY} already exists; "
            "use --force only when intentional rotation is required."
        )
        return 0

    write_atomically(env_path, updated)
    print(f"Updated {TOKEN_KEY} in {env_path}.")
    if args.force:
        print(
            "Token rotated: re-sync the ExternalSecrets and restart the webhook "
            "EventSource so both sides use the new value."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
