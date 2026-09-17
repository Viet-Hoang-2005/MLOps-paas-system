"""Regression checks for the service-owned logging contract."""

import asyncio
import io
import json
import logging
import os
import time
import unittest
from unittest.mock import patch

from src.logging_utils import (
    ConsoleFormatter,
    JsonFormatter,
    RuntimeLog,
    bind_context,
    configure,
    current_context,
    log_event,
    request_id,
    reset_context,
    sanitize,
)


class LoggingTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.logger = logging.Logger("test", logging.DEBUG)
        handler = logging.StreamHandler(self.output)
        handler.setFormatter(ConsoleFormatter("test"))
        self.logger.addHandler(handler)

    def test_format_context_escaping_and_allowlist(self):
        token = bind_context(request_id="req-1", features="must-not-appear")
        try:
            log_event(
                self.logger,
                "INFO",
                "job.completed",
                'Đã xong\nnext="value"\x00',
                duration_ms=12,
                features={"secret-data": 1},
            )
        finally:
            reset_context(token)
        line = self.output.getvalue()
        self.assertEqual(len(line.splitlines()), 1)
        self.assertRegex(line, r"^\d{4}-\d{2}-\d{2}T.*Z \[INFO\]: ")
        self.assertIn("\\n", line)
        self.assertIn("\\u0000", line)
        self.assertNotIn("request_id=", line)
        self.assertNotIn("features", line)
        self.assertEqual(current_context(), {})

    def test_json_format_keeps_metadata_and_numeric_fields(self):
        output = io.StringIO()
        logger = logging.Logger("json-test", logging.DEBUG)
        handler = logging.StreamHandler(output)
        handler.setFormatter(JsonFormatter("test"))
        logger.addHandler(handler)
        token = bind_context(request_id="request-1", project_id="project-1")
        try:
            log_event(logger, "WARNING", "job.retrying", "Job retry scheduled", attempt=2, duration_ms=12)
        finally:
            reset_context(token)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["service"], "test")
        self.assertEqual(payload["event"], "job.retrying")
        self.assertEqual(payload["request_id"], "request-1")
        self.assertEqual(payload["project_id"], "project-1")
        self.assertEqual(payload["attempt"], 2)
        self.assertEqual(payload["duration_ms"], 12)
        self.assertTrue(payload["ts"].endswith("Z"))
        self.assertNotIn("features", payload)

    def test_credentials_and_payloads_are_redacted(self):
        fake = "test-" + "credential-123"
        with patch.dict(os.environ, {"TEST_SECRET": fake}):
            examples = [
                (f"failed {fake}", fake),
                ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
                ('{"password": "unsafe-value"}', "unsafe-value"),
                ("redis://user:unsafe-value@cache:6379/1", "unsafe-value"),
                (
                    "https://storage.test/path?X-Amz-Signature=unsafe-value",
                    "unsafe-value",
                ),
                ('request [parameters: {"features": "unsafe-value"}]', "unsafe-value"),
            ]
            for source, hidden in examples:
                with self.subTest(source=source):
                    self.assertNotIn(hidden, sanitize(source))
        self.assertTrue(sanitize("x" * 5000).endswith("[truncated]"))

    def test_escaped_credential_quotes_do_not_leak_suffix(self):
        for value in (
            '{"password":"first\\"private-suffix"}',
            "password='first\\'private-suffix'",
        ):
            self.assertNotIn("private-suffix", sanitize(value))

    def test_partial_private_keys_are_masked_per_stream(self):
        saved = []
        runtime = RuntimeLog(self.logger, lambda line: saved.append(line) or True)
        runtime.detail("-----BEGIN PRIVATE KEY-----")
        runtime.detail("private-base64-body")
        runtime.detail("-----END PRIVATE KEY-----")
        runtime.detail("useful failure diagnosis")
        self.assertNotIn("private-base64-body", str(saved))
        self.assertIn("useful failure diagnosis", saved)
        self.assertIn("[REDACTED_PRIVATE_KEY]", saved)

    def test_detail_keeps_diagnostic_tail_of_large_chunks(self):
        saved = []
        runtime = RuntimeLog(self.logger, lambda line: saved.append(line) or True)
        runtime.detail("x" * 20000 + "\nuseful last error")
        self.assertEqual(saved[-1], "useful last error")
        self.assertLess(len(saved[0]), 2100)

    def test_protocol_stays_valid_json_for_token_named_metrics(self):
        runtime = RuntimeLog(self.logger)
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            runtime.protocol(
                'METRIC_JSON {"tokens_per_second":123,"api_token":"private-value"}'
            )
        payload = json.loads(output.getvalue().split(" ", 1)[1])
        self.assertEqual(payload["tokens_per_second"], 123)
        self.assertEqual(payload["api_token"], "[REDACTED]")
        self.assertNotIn("private-value", output.getvalue())

    def test_protocol_camelcase_secrets_keys_and_newlines(self):
        raw = ' \nMETRIC_JSON \n{"apiToken":"private-value","tokens_per_second":3,"https://storage.test/?token=private-key":1}'
        safe = sanitize(raw, limit=65536)
        self.assertEqual(len(safe.splitlines()), 1)
        self.assertTrue(safe.startswith("METRIC_JSON "))
        self.assertNotIn("private-value", safe)
        self.assertNotIn("private-key", safe)
        self.assertEqual(json.loads(safe.split(" ", 1)[1])["tokens_per_second"], 3)

    def test_detail_redacts_multiline_credentials_before_splitting(self):
        saved = []
        runtime = RuntimeLog(self.logger, lambda line: saved.append(line) or True)
        runtime.detail('password="first\nprivate-tail"\nuseful error')
        runtime.detail('[parameters: {\n"features":"private-payload"}]')
        self.assertNotIn("private-tail", str(saved))
        self.assertNotIn("private-payload", str(saved))
        self.assertIn("useful error", saved)

    def test_long_nonmatching_input_is_not_quadratic(self):
        started = time.monotonic()
        sanitize("x" * 100000)
        self.assertLess(time.monotonic() - started, 2.0)

    def test_traceback_contains_locations_not_source_or_locals(self):
        try:
            raise ValueError("private-payload")
        except ValueError:
            log_event(self.logger, "ERROR", "job.failed", "Job failed", exc_info=True)
        value = self.output.getvalue()
        self.assertIn("error=ValueError", value)
        self.assertIn("traceback:", value)
        self.assertNotIn("private-payload", value)
        self.assertEqual(len(value.splitlines()), 1)

    def test_runtime_sink_failure_preserves_details_and_protocol(self):
        saved = []

        def writer(line):
            saved.append(line)
            return True

        runtime = RuntimeLog(self.logger, writer)
        runtime.detail('password="unsafe-value"')
        self.assertNotIn("unsafe-value", saved[0])
        self.assertIn("[DEBUG]:", self.output.getvalue())
        self.output.truncate(0)
        self.output.seek(0)

        def broken(line):
            raise OSError("Redis unavailable")

        runtime.writer = broken
        runtime.detail("epoch 1 completed")
        self.assertIn("[INFO]:", self.output.getvalue())
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            runtime.protocol("BUILD_EOF_SUCCESS")
            runtime.protocol('METRIC_JSON {"cpu_percent":1.0}')
        self.assertEqual(
            output.getvalue().splitlines(),
            ["BUILD_EOF_SUCCESS", 'METRIC_JSON {"cpu_percent":1.0}'],
        )

    def test_configuration_is_idempotent_and_uses_info(self):
        root = logging.getLogger()
        previous, level = root.handlers[:], root.level
        try:
            with patch("sys.stdout", self.output):
                configure("test")
                configure("test")
                log_event(logging.getLogger("test"), "INFO", "service.ready", "Ready")
            self.assertEqual(root.level, logging.INFO)
            self.assertEqual(len(root.handlers), 1)
            self.assertEqual(self.output.getvalue().count("Ready"), 1)
        finally:
            root.handlers[:], root.level = previous, level

    def test_request_id_is_bounded_and_cannot_inject(self):
        self.assertEqual(request_id("request-1"), "request-1")
        self.assertNotIn("\n", request_id("a\nevent=fake"))
        self.assertEqual(len(request_id("x" * 500)), 36)

    def test_async_context_isolation_and_exception_reset(self):
        async def worker(value):
            token = bind_context(request_id=value)
            try:
                await asyncio.sleep(0)
                self.assertEqual(current_context()["request_id"], value)
            finally:
                reset_context(token)

        async def run():
            await asyncio.gather(worker("a"), worker("b"))

        asyncio.run(run())
        self.assertEqual(current_context(), {})
