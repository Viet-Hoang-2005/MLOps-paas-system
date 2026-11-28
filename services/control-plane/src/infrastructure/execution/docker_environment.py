import os


def _logging_environment():
    # Forward formatting and summary controls; each child logs at INFO.
    return {
        "LOG_FORMAT": os.environ.get("LOG_FORMAT") or "console",
        "LOG_SUMMARY_INTERVAL_SECONDS": os.environ.get("LOG_SUMMARY_INTERVAL_SECONDS") or "60",
    }
