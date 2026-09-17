"""Low-level resource sampling helpers."""

from pathlib import Path


def read_int_file(path: str) -> int | None:
    try:
        value = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if value in {"", "max"}:
        return None
    try:
        return int(value)
    except ValueError:
        return None
