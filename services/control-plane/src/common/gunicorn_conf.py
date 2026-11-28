"""Gunicorn logging configuration; HTTP access logs belong to Django middleware."""

import logging
import os
import pathlib

from prometheus_client import multiprocess

from common.logging import configure_logging
from common.logging_utils import get_logger, log_event

accesslog = None
errorlog = "-"


def _configure():
    configure_logging()
    for name in ("gunicorn.error", "gunicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True


def on_starting(server):
    multiproc_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if multiproc_dir:
        path = pathlib.Path(multiproc_dir)
        path.mkdir(parents=True, exist_ok=True)
        for db_file in path.glob("*.db"):
            db_file.unlink(missing_ok=True)
    _configure()
    log_event(get_logger(__name__), "INFO", "service.starting", "Control Plane server starting")


def post_fork(server, worker):
    _configure()


def child_exit(server, worker):
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        multiprocess.mark_process_dead(worker.pid)


def on_exit(server):
    log_event(get_logger(__name__), "INFO", "service.stopped", "Control Plane server stopped")
