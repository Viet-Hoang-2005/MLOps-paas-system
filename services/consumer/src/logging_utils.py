import atexit
import contextvars
import json
import logging
import math
import os
import re
import sys
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import cast
from urllib.parse import urlsplit, urlunsplit

_context: contextvars.ContextVar[dict[str, object]] = contextvars.ContextVar(
    "mlops_log_context", default={}
)
_service = "backend"
_output_lock = threading.RLock()
_SECRET_KEY = (
    r"(?:authorization|x-api-key|password|passwd|secret|token|api[_-]?key|"
    r"credential|signature|capability|access[_-]?key|private[_-]?key)"
)
_SECRETS = re.compile(
    r"(?i)((?<![\w-])[\w-]{0,96}"
    + _SECRET_KEY
    + r"[\w-]{0,96}[\"\x27]?\s*[:=]\s*)(?:\"(?:\\.|[^\"\\])*\"|\x27(?:\\.|[^\x27\\])*\x27|[^\s,;}]+)"
)
_URL = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]{0,31}://[^\s<>\"']+")
_SAFE_VALUE = re.compile(r"^[a-zA-Z0-9_.:/@+-]+$")
_PROTOCOL = re.compile(r"^(\s*METRIC_JSON(?::| )\s*)(.*)$", re.S)
_FIELDS = frozenset(
    {
        "request_id",
        "celery_task_id",
        "tenant_id",
        "project_id",
        "model_version_id",
        "build_id",
        "training_job_id",
        "drift_run_id",
        "deployment_id",
        "resource_id",
        "backend",
        "attempt",
        "duration_ms",
        "error_type",
        "error_code",
        "status",
        "status_code",
        "method",
        "route",
        "retry_seconds",
        "exit_code",
        "source",
        "dependency",
        "partition",
        "offset",
        "count",
        "records",
        "batches",
        "published",
        "persisted",
        "committed",
        "successes",
        "failures",
        "retries",
        "suppressed",
        "window_seconds",
        "error_key",
        "drift_detected",
        "drift_share",
        "samples",
        "reference_samples",
        "production_samples",
        "features_count",
        "reason",
        "operation",
        "error_count",
    }
)


def _after_fork():
    global _output_lock
    _output_lock = threading.RLock()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork)


def _protocol_value(value):
    if isinstance(value, dict):
        return {
            sanitize(key): "[REDACTED]"
            if re.search(_SECRET_KEY, key, re.I)
            and not (
                isinstance(item, (int, float))
                and re.fullmatch(
                    r"(?i)(?:tokens?_per_second|tokens?_count|total_tokens|num_tokens)",
                    key,
                )
            )
            else _protocol_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_protocol_value(item) for item in value]
    return sanitize(value) if isinstance(value, str) else value


def sanitize(value, limit=2048):
    """Defence in depth: callers must never submit data/HTTP payloads to logging."""
    try:
        text = str(value)
    except Exception:
        return "[unprintable]"
    protocol = _PROTOCOL.match(text)
    if protocol:
        try:
            payload = _protocol_value(json.loads(protocol.group(2)))
            prefix = "METRIC_JSON:" if ":" in protocol.group(1) else "METRIC_JSON "
            encoded = prefix + json.dumps(
                payload, separators=(",", ":"), ensure_ascii=True
            )
            return (
                encoded
                if limit is None or len(encoded) <= limit
                else "[protocol record exceeds log limit]"
            )
        except (ValueError, RecursionError):
            return "[invalid metric protocol record]"
    for name, secret in os.environ.items():
        if re.search(_SECRET_KEY, name, re.I) and len(secret) >= 6:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(
        r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
        "[REDACTED]",
        text,
        flags=re.S,
    )
    text = re.sub(r"-----BEGIN [^-]*PRIVATE KEY-----.*", "[REDACTED]", text, flags=re.S)
    text = re.sub(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9+/_.=~-]+", r"\1 [REDACTED]", text)
    text = re.sub(
        r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[REDACTED]", text
    )

    def safe_url(match):
        try:
            parts = urlsplit(match.group())
            return urlunsplit(
                (parts.scheme, parts.hostname or "redacted", "/[REDACTED]", "", "")
            )
        except ValueError:
            return "[REDACTED_URL]"

    text = _URL.sub(safe_url, text)
    text = _SECRETS.sub(r"\1[REDACTED]", text)
    text = re.sub(r"(?is)\[SQL:.*", "[database details omitted]", text)
    text = re.sub(r"(?is)\[parameters:.*", "[database parameters omitted]", text)
    return (
        text if limit is None or len(text) <= limit else text[:limit] + "...[truncated]"
    )


def current_context():
    return dict(_context.get())


def bind_context(**fields):
    return _context.set(
        {**_context.get(), **{k: v for k, v in fields.items() if k in _FIELDS}}
    )


def reset_context(token):
    _context.reset(token)


def request_id(value=None):
    value = str(value or "")
    return value if re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value) else str(uuid.uuid4())


def _encode(value):
    text = sanitize(value)
    if _SAFE_VALUE.fullmatch(text):
        return text
    encoded = json.dumps(text, ensure_ascii=False)
    for separator in ("\x85", "\u2028", "\u2029"):
        encoded = encoded.replace(separator, "\\u%04x" % ord(separator))
    return encoded


def _record_fields(record, service):
    fields = {
        "ts": datetime.fromtimestamp(record.created, timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "level": record.levelname,
        "service": service or _service,
        "event": getattr(record, "event", "application.log"),
        "instance": os.environ.get("HOSTNAME", "local"),
        "pid": os.getpid(),
    }
    context = current_context()
    for env_key in (
        "PROJECT_ID",
        "MODEL_VERSION_ID",
        "BUILD_ID",
        "TRAINING_JOB_ID",
        "DRIFT_RUN_ID",
    ):
        if os.environ.get(env_key):
            context.setdefault(env_key.lower(), os.environ[env_key])
    for key in sorted(_FIELDS):
        value = getattr(record, key, context.get(key))
        if value is not None and value != "":
            fields[key] = value
    fields["msg"] = sanitize(record.getMessage())
    if record.exc_info:
        error_type, _, tb = record.exc_info
        fields["error_type"] = error_type.__name__ if error_type else "Exception"
        locations = []
        while tb is not None:
            code = tb.tb_frame.f_code
            locations.append(f"{os.path.basename(code.co_filename)}:{tb.tb_lineno}:{code.co_name}")
            tb = tb.tb_next
        fields["traceback"] = " <- ".join(locations[-30:])
    return fields


def _display(value):
    """Render text safely as a single, human-readable physical log line."""
    encoded = json.dumps(sanitize(value), ensure_ascii=False)[1:-1]
    for separator in ("\x85", "\u2028", "\u2029"):
        encoded = encoded.replace(separator, "\\u%04x" % ord(separator))
    return encoded


def _json_value(value):
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    return sanitize(value)


def log_format():
    """Return the supported container formatter, defaulting safely to console."""
    return "json" if os.environ.get("LOG_FORMAT", "console").strip().lower() == "json" else "console"


class ConsoleFormatter(logging.Formatter):
    def __init__(self, service=None):
        super().__init__()
        self.service = service

    def format(self, record):
        fields = _record_fields(record, self.service)
        details = []
        if fields.get("error_type"):
            details.append(f"error={_display(fields['error_type'])}")
        if fields.get("reason"):
            details.append(_display(fields["reason"]))
        if fields.get("status_code"):
            details.append(f"HTTP {fields['status_code']}")
        if fields.get("retry_seconds") is not None:
            attempt = fields.get("attempt")
            prefix = f"retry {attempt} in" if attempt is not None else "retry in"
            details.append(f"{prefix} {_display(fields['retry_seconds'])}s")
        if fields.get("traceback"):
            details.append(f"traceback: {_display(fields['traceback'])}")
        suffix = f" — {'; '.join(details)}" if details else ""
        return f"{fields['ts']} [{fields['level']}]: {_display(fields['msg'])}{suffix}"


class JsonFormatter(logging.Formatter):
    def __init__(self, service=None):
        super().__init__()
        self.service = service

    def format(self, record):
        fields = _record_fields(record, self.service)
        return json.dumps(
            {key: _json_value(value) for key, value in fields.items()},
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )


def formatter_for(service=None):
    return JsonFormatter(service) if log_format() == "json" else ConsoleFormatter(service)


class SafeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        with _output_lock:
            super().emit(record)

    def handleError(self, record):
        pass  # Logging failure must not stop the workload or recurse to stderr.


class FrameworkFilter(logging.Filter):
    def filter(self, record):
        # These request exceptions are owned by the ASGI boundary; keep startup,
        # worker and other framework errors, but don't repeat each request trace.
        return not (
            record.name == "uvicorn.error"
            and record.getMessage().startswith("Exception in ASGI application")
        )


def configure(service):
    global _service
    _service = service
    root = logging.getLogger()
    handler = SafeStreamHandler(sys.stdout)
    handler.setFormatter(formatter_for(service))
    handler.addFilter(FrameworkFilter())
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    for name in (
        "gunicorn.error",
        "uvicorn",
        "uvicorn.error",
        "celery",
        "django",
        "bentoml",
    ):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(logging.NOTSET)
    for name in (
        "gunicorn.access",
        "uvicorn.access",
        "bentoml.access",
        "celery.app.trace",
        "celery.worker.strategy",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
    for name in (
        "urllib3",
        "httpx",
        "httpcore",
        "botocore",
        "boto3",
        "sqlalchemy",
        "mlflow",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
    return logging.getLogger(service)


def get_logger(name):
    return logging.getLogger(name)


def log_event(logger, level, event, message, **fields):
    exc_info = fields.pop("exc_info", None)
    level = (
        getattr(logging, level.upper(), logging.INFO)
        if isinstance(level, str)
        else level
    )
    logger.log(
        level,
        message,
        extra={"event": event, **{k: v for k, v in fields.items() if k in _FIELDS}},
        exc_info=exc_info,
    )


def _summary_message(event, counts, elapsed):
    label = event.replace(".", " ").replace("_", " ").capitalize()
    parts = []
    for key, word in (
        ("successes", "succeeded"),
        ("failures", "failed"),
        ("records", "records"),
        ("batches", "batches"),
        ("published", "published"),
        ("persisted", "persisted"),
        ("committed", "committed"),
        ("retries", "retries"),
        ("error_count", "errors"),
        ("suppressed", "repeated errors suppressed"),
    ):
        value = counts.get(key)
        if value:
            parts.append(f"{value} {word}")
    return f"{label}: {', '.join(parts) or 'no activity'} over {round(elapsed, 3)}s"


class Summary:
    """Bounded per-process counters; never an authoritative metric store."""

    def __init__(self, logger, event, interval=None):
        self.logger, self.event = logger, event
        try:
            self.interval = max(
                1.0,
                float(interval or os.environ.get("LOG_SUMMARY_INTERVAL_SECONDS", "60")),
            )
            if not math.isfinite(self.interval):
                self.interval = 60.0
        except ValueError:
            self.interval = 60.0
        self._reset()
        atexit.register(self.close)
        if hasattr(os, "register_at_fork"):
            os.register_at_fork(after_in_child=self._reset)

    def _reset(self):
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = None
        # Counter supports fractional durations; its stubs restrict values to int.
        self.counts = cast(dict[str, int | float], Counter())
        self.errors = {}
        self.last_error = {}
        self.last_recovery = {}
        self.started = time.monotonic()

    def _start(self):
        if self.thread is None and not self.stop.is_set():
            self.thread = threading.Thread(
                target=self._run, name="log-summary", daemon=True
            )
            self.thread.start()

    def _run(self):
        while not self.stop.wait(self.interval):
            self.flush()

    def record(self, success=True, duration_ms=0, **numeric_counts):
        with self.lock:
            self._start()
            self.counts["successes" if success else "failures"] += 1
            self.counts["duration_ms"] += max(0, duration_ms)
            for key, value in numeric_counts.items():
                if key in _FIELDS and isinstance(value, (int, float)):
                    self.counts[key] += value

    def failure(self, key, message, **fields):
        level = fields.pop("level", "WARNING")
        severity = (
            getattr(logging, level.upper(), logging.WARNING)
            if isinstance(level, str)
            else level
        )
        with self.lock:
            self._start()
            overflow = key not in self.last_error and len(self.last_error) >= 64
            key = (
                ("other.ERROR" if severity >= logging.ERROR else "other.WARNING")
                if overflow
                else key
            )
            now = time.monotonic()
            first = (key not in self.errors or overflow) and now - self.last_error.get(
                key, float("-inf")
            ) >= self.interval
            self.errors[key] = self.errors.get(key, 0) + 1
            self.counts["error_count"] += 1
            if first:
                self.last_error[key] = now
            else:
                self.counts["suppressed"] += 1
        if first:
            log_event(
                self.logger,
                level,
                self.event + ".error",
                message,
                error_key=key,
                **fields,
            )

    def recovery(self, key, **fields):
        with self.lock:
            count = self.errors.pop(key, 0)
            now = time.monotonic()
            emit = (
                count
                and now - self.last_recovery.get(key, float("-inf")) >= self.interval
            )
            if emit:
                self.last_recovery[key] = now
        if emit:
            log_event(
                self.logger,
                "INFO",
                self.event + ".recovered",
                f"{self.event.replace('.', ' ').capitalize()} recovered after {count} failure(s)",
                error_key=key,
                count=count,
                **fields,
            )

    def flush(self):
        with self.lock:
            counts, self.counts = self.counts, cast(dict[str, int | float], Counter())
            now = time.monotonic()
            elapsed, self.started = now - self.started, now
        if counts:
            log_event(
                self.logger,
                "INFO",
                self.event,
                _summary_message(self.event, counts, elapsed),
                window_seconds=round(elapsed, 3),
                **counts,
            )

    def close(self):
        self.stop.set()
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join(timeout=1)
        self.flush()
