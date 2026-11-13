"""Training subprocess metric protocol."""

import json


def is_metric_protocol_line(message: str) -> bool:
    if "\n" in message or "\r" in message or len(message) > 16384:
        return False
    stripped = message.lstrip()
    for prefix in ("METRIC_JSON:", "METRIC_JSON "):
        if stripped.startswith(prefix):
            try:
                return isinstance(json.loads(stripped[len(prefix) :]), dict)
            except (ValueError, RecursionError):
                return False
    return False
