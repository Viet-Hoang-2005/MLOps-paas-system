import argparse
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from src.logging_utils import log_format


def server_log_config(service):
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "application": {
                "()": "src.logging_utils.JsonFormatter"
                if log_format() == "json"
                else "src.logging_utils.ConsoleFormatter",
                "service": service,
            }
        },
        "filters": {"framework": {"()": "src.logging_utils.FrameworkFilter"}},
        "handlers": {
            "console": {
                "class": "src.logging_utils.SafeStreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "application",
                "filters": ["framework"],
            }
        },
        "root": {"handlers": ["console"], "level": "INFO"},
        "loggers": {
            "uvicorn": {"handlers": [], "propagate": True},
            "uvicorn.error": {"handlers": [], "propagate": True},
            "uvicorn.access": {"handlers": [], "propagate": False},
        },
    }


@contextmanager
def metrics_directory():
    """Parent-only startup: each server run gets fresh, pod-local metric files.

    Uvicorn spawn inherits the environment before importing the application.
    Worker restarts keep the same directory/counter; server restarts do not.
    Never clear shared files from worker lifespan handlers.
    """
    root = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if root:
        Path(root).mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="model-server-metrics-", dir=root) as directory:
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = directory
        try:
            yield directory
        finally:
            if root is None:
                os.environ.pop("PROMETHEUS_MULTIPROC_DIR", None)
            else:
                os.environ["PROMETHEUS_MULTIPROC_DIR"] = root


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    parser.add_argument("--service", required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    with metrics_directory():
        import uvicorn  # Import only after setting the inherited metrics directory.

        uvicorn.run(
            args.app,
            host=args.host,
            port=args.port,
            workers=args.workers,
            access_log=False,
            log_config=server_log_config(args.service),
        )


if __name__ == "__main__":
    main()
