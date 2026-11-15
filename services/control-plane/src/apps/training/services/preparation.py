"""Bounded S3 I/O and Celery execution for immutable Input preparation."""

from time import monotonic

from botocore.config import Config
from celery import shared_task

from infrastructure.storage import S3Storage


class PreparationStorage(S3Storage):
    def __init__(self, checkpoint):
        super().__init__(client_config=Config(
            connect_timeout=10, read_timeout=30,
            retries={"mode": "standard", "total_max_attempts": 2},
        ))
        self.checkpoint = checkpoint

    def read(self, uri, max_bytes=4 * 1024 * 1024):
        self.checkpoint()
        body, _, _ = self.open_stream(uri)
        chunks = bytearray()
        next_check = monotonic()
        try:
            while True:
                if monotonic() >= next_check:
                    self.checkpoint()
                    next_check = monotonic() + 1
                chunk = body.read(min(1024 * 1024, max_bytes + 1 - len(chunks)))
                if not chunk:
                    break
                chunks.extend(chunk)
                if len(chunks) > max_bytes:
                    raise ValueError("Object exceeds the allowed read size.")
            self.checkpoint()
            return bytes(chunks)
        finally:
            body.close()

    def put(self, *args, **kwargs):
        self.checkpoint()
        result = super().put(*args, **kwargs)
        self.checkpoint()
        return result


@shared_task(soft_time_limit=540, time_limit=570, max_retries=0, reject_on_worker_lost=False)
def prepare_training_input(job_id, token):
    from .drafts import prepare_workspace

    # The service fences failures and schedules cleanup before raising.
    # Never autoretry dataset downloads or log exception text containing S3 URLs.
    try:
        job = prepare_workspace(job_id, token)
        return job.status if job else "ignored"
    except Exception:
        return "failed"
