import contextvars
import json
import logging
import math
import os
import re
import sys
import threading
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

_context: contextvars.ContextVar[dict[str, object]] = contextvars.ContextVar("mlops_log_context", default={})
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


class RuntimeLog:
    """Separate readable job output from concise operational container events."""

    def __init__(self, logger, writer=None):
        self.logger, self.writer = logger, writer
        self._private_key_streams = set()

    def _write(self, line):
        if self.writer is None:
            return False
        try:
            return self.writer(line) is True
        except Exception:
            return False

    def detail(self, message):
        # Redact before per-line truncation; never discard the tail of a chunk.
        stream = threading.get_ident()
        lines = []
        for line in str(message).splitlines():
            starts_key = bool(re.search(r"-----BEGIN [^-]*PRIVATE KEY-----", line))
            if starts_key or stream in self._private_key_streams:
                if starts_key:
                    self._private_key_streams.add(stream)
                if re.search(r"-----END [^-]*PRIVATE KEY-----", line):
                    self._private_key_streams.discard(stream)
                if not starts_key:
                    continue
                line = "[REDACTED_PRIVATE_KEY]"
            lines.append(line)
        # Quoted credential values and SQL parameter dumps may span lines.
        # Sanitize the whole chunk before splitting/truncating presentation lines.
        for line in sanitize("\n".join(lines), limit=None).splitlines():
            safe = sanitize(line)
            delivered = self._write(safe)
            log_event(
                self.logger,
                "DEBUG" if delivered else "INFO",
                "runtime.output",
                safe,
                source="untrusted",
            )

    def event(self, level, event, message, **fields):
        details = [sanitize(message)]
        for key in ("reason", "error_type", "error_code", "status_code", "exit_code"):
            if fields.get(key) is not None:
                details.append(f"{key}={_encode(fields[key])}")
        self._write(sanitize(" ".join(details)))
        log_event(self.logger, level, event, message, **fields)

    def protocol(self, message):
        safe = sanitize(message, limit=65536)
        self._write(safe)
        try:
            with _output_lock:
                sys.stdout.write(safe + "\n")
                sys.stdout.flush()
        except (OSError, ValueError):
            pass
