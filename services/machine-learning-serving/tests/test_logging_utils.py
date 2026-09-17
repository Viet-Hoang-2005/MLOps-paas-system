"""Regression checks for the service-owned logging contract."""

import asyncio
import io
import json
import logging
import os
import threading
import time
import unittest
from unittest.mock import patch

from src.logging_utils import (
    ConsoleFormatter,
    JsonFormatter,
    RequestLoggingMiddleware,
    Summary,
    bind_context,
    configure,
    current_context,
    log_event,
    request_id,
    reset_context,
    sanitize,
)


class LoggingTests(unittest.TestCase):
    def test_entrypoint_uses_local_worker_configuration(self):
        from src.uvicorn_entrypoint import main

        with patch(
            "sys.argv",
            [
                "uvicorn_entrypoint",
                "src.main:app",
                "--service",
                "machine-learning-serving",
                "--port",
                "8050",
                "--workers",
                "2",
            ],
        ), patch("uvicorn.run") as run:
            main()
        self.assertEqual(run.call_args.args, ("src.main:app",))
        self.assertEqual(run.call_args.kwargs["workers"], 2)
        self.assertFalse(run.call_args.kwargs["access_log"])
        self.assertEqual(
            run.call_args.kwargs["log_config"]["handlers"]["console"]["class"],
            "src.logging_utils.SafeStreamHandler",
        )

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

    def test_console_format_includes_http_access_metadata(self):
        log_event(
            self.logger,
            "DEBUG",
            "http.request.finished",
            "HTTP request finished",
            method="POST",
            route="/predict",
            status_code=200,
            duration_ms=12.5,
        )
        line = self.output.getvalue()
        self.assertIn("POST /predict; HTTP 200; duration=12.5ms", line)
        self.assertEqual(len(line.splitlines()), 1)

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

    def test_protocol_camelcase_secrets_keys_and_newlines(self):
        raw = ' \nMETRIC_JSON \n{"apiToken":"private-value","tokens_per_second":3,"https://storage.test/?token=private-key":1}'
        safe = sanitize(raw, limit=65536)
        self.assertEqual(len(safe.splitlines()), 1)
        self.assertTrue(safe.startswith("METRIC_JSON "))
        self.assertNotIn("private-value", safe)
        self.assertNotIn("private-key", safe)
        self.assertEqual(json.loads(safe.split(" ", 1)[1])["tokens_per_second"], 3)

    def test_long_nonmatching_input_is_not_quadratic(self):
        started = time.monotonic()
        sanitize("x" * 100000)
        self.assertLess(time.monotonic() - started, 2.0)

    def test_overflow_does_not_hide_server_errors_behind_warnings(self):
        summary = Summary(self.logger, "overflow", interval=60)
        try:
            for n in range(65):
                summary.failure(f"client-{n}", "Client rejected")
            summary.failure("new-server", "Server failed", level="ERROR")
            self.assertIn("Server failed", self.output.getvalue())
            before = self.output.getvalue().count("Server failed")
            with patch(
                "src.logging_utils.time.monotonic", return_value=time.monotonic() + 120
            ):
                summary.failure("another-server", "Server failed", level="ERROR")
            self.assertEqual(
                self.output.getvalue().count("Server failed"), before + 1
            )
            self.assertLessEqual(len(summary.last_error), 66)
        finally:
            summary.close()

    def test_flapping_is_bounded_within_a_window(self):
        summary = Summary(self.logger, "flapping", interval=3600)
        for _ in range(1000):
            summary.failure("database", "Database unavailable")
            summary.recovery("database")
        self.assertEqual(len(self.output.getvalue().splitlines()), 2)
        summary.close()
        self.assertIn("1000 errors", self.output.getvalue())
        self.assertIn("999 repeated errors suppressed", self.output.getvalue())

    def test_summary_multithread_counts(self):
        summary = Summary(self.logger, "parallel", interval=3600)

        def run():
            for _ in range(100):
                summary.record(records=1)

        threads = [threading.Thread(target=run) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        summary.close()
        self.assertIn("400 records", self.output.getvalue())

    def test_uvicorn_configuration_uses_local_handler(self):
        from src.uvicorn_entrypoint import server_log_config

        config = server_log_config("model-server")
        self.assertEqual(
            config["handlers"]["console"]["class"],
            "src.logging_utils.SafeStreamHandler",
        )
        self.assertEqual(config["formatters"]["application"]["service"], "model-server")
        self.assertEqual(
            config["formatters"]["application"]["()"], "src.logging_utils.ConsoleFormatter"
        )
        self.assertFalse(config["loggers"]["uvicorn.access"]["propagate"])

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

    def test_summary_empty_success_failure_recovery_and_close(self):
        summary = Summary(self.logger, "ingestion.summary", interval=3600)
        summary.flush()
        self.assertEqual(self.output.getvalue(), "")
        for _ in range(1000):
            summary.record(records=2, duration_ms=1)
        self.assertEqual(self.output.getvalue(), "")
        summary.failure("database", "Database unavailable")
        for _ in range(9):
            summary.failure("database", "Database unavailable")
        self.assertEqual(len(self.output.getvalue().splitlines()), 1)
        summary.flush()
        self.assertIn("2000 records", self.output.getvalue())
        self.assertIn("1000 succeeded", self.output.getvalue())
        self.assertIn("9 repeated errors suppressed", self.output.getvalue())
        summary.recovery("database")
        summary.recovery("database")
        self.assertEqual(
            self.output.getvalue().count("Ingestion summary recovered"), 1
        )
        summary.close()
        summary.close()

    def test_summary_bounded_error_keys_and_fork_reset(self):
        summary = Summary(self.logger, "summary", interval=3600)
        for n in range(100):
            summary.failure(str(n), "Unavailable")
        self.assertLessEqual(len(summary.errors), 65)
        summary.close()
        summary._reset()
        self.assertEqual(dict(summary.counts), {})
        self.assertIsNone(summary.thread)
        summary.close()

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

    def test_asgi_probe_suppression_and_error_context(self):
        async def app(scope, receive, send):
            self.assertIn("request_id", current_context())
            await send(
                {"type": "http.response.start", "status": scope.get("test_status", 200)}
            )
            await send({"type": "http.response.body", "body": b""})

        async def noop(*args):
            pass

        middleware = RequestLoggingMiddleware(app)
        middleware.logger = self.logger
        predict_route = type("Route", (), {"path": "/predict"})()
        health_route = type("Route", (), {"path": "/health"})()

        async def run():
            await middleware(
                {"type": "http", "path": "/health", "method": "GET", "route": health_route},
                noop,
                noop,
            )
            await middleware(
                {"type": "http", "path": "/health", "method": "GET", "route": health_route, "test_status": 500},
                noop,
                noop,
            )
            await middleware(
                {"type": "http", "path": "/predict", "method": "GET", "route": predict_route},
                noop,
                noop,
            )

        asyncio.run(run())
        output = self.output.getvalue()
        self.assertIn("GET /health; HTTP 500; duration=", output)
        self.assertIn("GET /predict; HTTP 200; duration=", output)
        self.assertNotIn("GET /health; HTTP 200", output)
        self.assertNotIn("request_id=", output)
        self.assertEqual(current_context(), {})

    def test_asgi_route_resolver_uses_template(self):
        class Candidate:
            path = "/models/{version_id}/predict"

            @staticmethod
            def matches(scope):
                return type("Match", (), {"name": "FULL"})(), {}

        middleware = RequestLoggingMiddleware(lambda *_: None, routes=[Candidate()])
        self.assertEqual(
            middleware._route({"type": "http", "path": "/models/private-id/predict"}),
            "/models/{version_id}/predict",
        )
