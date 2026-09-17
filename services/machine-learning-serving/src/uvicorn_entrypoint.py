"""Configure Uvicorn before it emits startup logs, including spawned workers."""

import argparse

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


def main():
    import uvicorn  # Provided by this service.

    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    parser.add_argument("--service", required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
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
