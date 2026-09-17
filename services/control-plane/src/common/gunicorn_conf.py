"""Gunicorn logging configuration; HTTP access logs belong to Django middleware."""

import logging

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
    _configure()
    log_event(get_logger(__name__), "INFO", "service.starting", "Control Plane server starting")


def post_fork(server, worker):
    _configure()


def on_exit(server):
    log_event(get_logger(__name__), "INFO", "service.stopped", "Control Plane server stopped")
