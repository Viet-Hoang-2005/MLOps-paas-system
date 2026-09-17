import logging
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from common import celery_logging, gunicorn_conf
from common import logging as app_logging
from common.logging_utils import bind_context, current_context, reset_context
from common.middleware import RequestContextMiddleware, request_id_context
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import ResolverMatch
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.models import Build
from apps.deployment.services import logs as deployment_logs
from apps.deployment.tasks import execute_build
from apps.drift.services import logs as drift_logs
from apps.training.models import TrainingJob
from apps.training.services import logs as training_logs
from apps.training.tasks import execute_training_job


@pytest.mark.parametrize("status", [200, 403, 500])
def test_request_context_roundtrip_and_cleanup(status):
    before = current_context()
    request = RequestFactory().get("/api/example/?token=never-log-this", HTTP_X_REQUEST_ID="request-123")
    request.resolver_match = ResolverMatch(lambda req: HttpResponse(), (), {}, route="api/example/")
    seen = []

    def respond(req):
        seen.append(current_context()["request_id"])
        return HttpResponse(status=status)

    middleware = RequestContextMiddleware(respond)
    response = middleware(request)
    assert seen == ["request-123"]
    assert response["X-Request-ID"] == "request-123"
    assert current_context() == before
    assert request_id_context.get() == ""


@pytest.mark.parametrize("value", ["x" * 129, "header\nforged=true", "Bearer hidden-value"])
def test_invalid_request_ids_are_replaced(value):
    request = RequestFactory().get("/api/example/", HTTP_X_REQUEST_ID=value)
    middleware = RequestContextMiddleware(lambda req: HttpResponse())
    response = middleware(request)
    assert str(uuid.UUID(response["X-Request-ID"])) == response["X-Request-ID"]


def test_exception_resets_request_context():
    before = current_context()
    middleware = RequestContextMiddleware(Mock(side_effect=RuntimeError("failed")))
    with pytest.raises(RuntimeError):
        middleware(RequestFactory().get("/api/example/"))
    assert current_context() == before
    assert request_id_context.get() == ""


@pytest.mark.parametrize("path", ["/health/live", "/health/ready", "/health/metrics"])
def test_successful_probes_do_not_create_access_log(path, caplog):
    middleware = RequestContextMiddleware(lambda req: HttpResponse())
    with caplog.at_level(logging.INFO):
        middleware(RequestFactory().get(path))
    assert not [record for record in caplog.records if getattr(record, "event", "").startswith("http.request")]


def test_successful_request_emits_info_access_log_without_summary(caplog):
    request = RequestFactory().get("/api/models/version-1/predict/?token=never-log-this")
    request.resolver_match = ResolverMatch(
        lambda req: HttpResponse(), (), {}, route="api/models/{version_id}/predict/"
    )
    middleware = RequestContextMiddleware(lambda req: HttpResponse())

    with caplog.at_level(logging.INFO):
        response = middleware(request)

    assert response.status_code == 200
    access_logs = [
        record
        for record in caplog.records
        if getattr(record, "event", "") == "http.request.finished"
    ]
    assert len(access_logs) == 1
    assert access_logs[0].method == "GET"
    assert access_logs[0].route == "api/models/{version_id}/predict/"
    assert access_logs[0].status_code == 200
    assert access_logs[0].duration_ms >= 0
    assert "never-log-this" not in caplog.text


def test_failed_probe_is_reported_immediately_each_time(caplog):
    middleware = RequestContextMiddleware(lambda req: HttpResponse(status=503))
    with caplog.at_level(logging.INFO):
        for _ in range(3):
            middleware(RequestFactory().get("/health/ready"))
    failures = [r for r in caplog.records if getattr(r, "event", "") == "http.request.failed"]
    assert len(failures) == 3
    assert all(record.levelno == logging.ERROR for record in failures)


@pytest.mark.parametrize("state", ["SUCCESS", "FAILURE", "RETRY", "REVOKED"])
def test_task_context_is_scoped_and_never_logs_arguments_or_results(state, monkeypatch):
    outer = bind_context(request_id="outer-request", tenant_id="outer-tenant")
    emitted = Mock()
    summary = Mock()
    monkeypatch.setattr(celery_logging, "log_event", emitted)
    monkeypatch.setattr(celery_logging, "task_summary", summary)
    task = SimpleNamespace(
        name="apps.training.tasks.execute_training_job",
        request=SimpleNamespace(
            headers={"mlops_context": {"request_id": "inner-request", "password": "hidden"}},
            retries=2,
        ),
    )
    job_id = str(uuid.uuid4())
    try:
        celery_logging.task_start(task_id="task-123", task=task, args=[job_id, "private-payload"])
        assert current_context()["request_id"] == "inner-request"
        assert current_context()["tenant_id"] is None
        assert current_context()["training_job_id"] == job_id
        assert current_context()["attempt"] == 3
        celery_logging.task_finish(task=task, state=state, retval={"token": "private-result"})
        assert current_context()["request_id"] == "outer-request"
        assert "private" not in str(emitted.call_args_list)
        assert "private" not in str(summary.mock_calls)
        assert summary.record.call_args.kwargs["success"] is (state == "SUCCESS")
        assert summary.record.call_args.kwargs["tasks"] == 1
        assert summary.record.call_args.kwargs["retries"] == (1 if state == "RETRY" else 0)
    finally:
        reset_context(outer)


def test_publish_propagates_only_bounded_correlation():
    token = bind_context(request_id="request-123", tenant_id="bad\nvalue", project_id="project-123")
    try:
        headers = {"existing": "untouched"}
        celery_logging.publish_context(headers=headers, body={"password": "private"})
        assert headers == {
            "existing": "untouched",
            "mlops_context": {"request_id": "request-123", "project_id": "project-123"},
        }
    finally:
        reset_context(token)


def test_retry_signal_emits_one_safe_warning_with_context(caplog):
    from celery.exceptions import Retry
    from celery.signals import task_retry
    from common.logging_utils import JsonFormatter

    task = Mock()
    task.name = "apps.training.tasks.execute_training_job"
    task.request = SimpleNamespace(headers={"mlops_context": {"request_id": "retry-request"}}, retries=2)
    job_id = str(uuid.uuid4())
    before = current_context()
    task_summary = Mock()
    monkeypatch.setattr(celery_logging, "task_summary", task_summary)
    with caplog.at_level(logging.DEBUG):
        celery_logging.task_start(task_id="retry-task", task=task, args=[job_id, "private-argument"])
        try:
            task_retry.send(
                sender=task,
                request=task.request,
                reason=Retry(message="private-reason", exc=RuntimeError("private-error"), when=12),
                args=["private-argument"],
                retval="private-result",
            )
            warnings = [record for record in caplog.records if record.levelno >= logging.WARNING]
            assert len(warnings) == 1
            warning = warnings[0]
            assert warning.levelno == logging.WARNING
            assert warning.event == "celery.task.retry"
            assert warning.attempt == 3
            assert warning.retry_seconds == 12
            rendered = JsonFormatter("control-plane").format(warning)
            assert f'"training_job_id":"{job_id}"' in rendered
            assert '"request_id":"retry-request"' in rendered
            assert '"celery_task_id":"retry-task"' in rendered
            assert "private" not in rendered
        finally:
            celery_logging.task_finish(task=task, state="RETRY", retval="private-result")
    assert current_context() == before
    assert len([record for record in caplog.records if record.levelno >= logging.WARNING]) == 1
    assert task_summary.record.call_args.kwargs["retries"] == 1


@pytest.mark.django_db
def test_lifecycle_logs_wait_for_commit_and_rollback_discards_them(monkeypatch, django_capture_on_commit_callbacks):
    emitted = Mock()
    monkeypatch.setattr(app_logging, "log_event", emitted)
    with django_capture_on_commit_callbacks(execute=True):
        token = bind_context(request_id="original-request")
        try:
            with transaction.atomic():
                app_logging.lifecycle_event(
                    "build.ready", resource_type="build", resource_id=uuid.uuid4(), status="ready"
                )
                emitted.assert_not_called()
        finally:
            reset_context(token)
    assert emitted.call_args.kwargs["request_id"] == "original-request"
    emitted.reset_mock()
    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(RuntimeError), transaction.atomic():
            app_logging.lifecycle_event(
                "build.failed", resource_type="build", resource_id=uuid.uuid4(), status="failed"
            )
            raise RuntimeError("rollback")
    emitted.assert_not_called()


@pytest.fixture
def project(db):
    owner = get_user_model().objects.create_user("logging@example.com", "test-password")
    return ModelProject.objects.create(owner=owner, name="logging")


def test_build_dispatch_is_not_completion(project, monkeypatch, django_capture_on_commit_callbacks):
    build = Build.objects.create(project=project, status="queued", backend="argo", flavor="sklearn")
    monkeypatch.setattr(
        "apps.deployment.tasks.build_backend", lambda _: SimpleNamespace(run=lambda _: {"dispatched": True})
    )
    emitted = Mock()
    monkeypatch.setattr(app_logging, "log_event", emitted)
    with django_capture_on_commit_callbacks(execute=True):
        assert execute_build.run(str(build.public_id)) == "building"
        emitted.assert_not_called()
    assert [c.args[2] for c in emitted.call_args_list] == ["build.building", "build.dispatched"]
    build.refresh_from_db()
    assert build.status == "building"
    assert build.completed_at is None


def test_training_dispatch_is_not_completion(project, monkeypatch, django_capture_on_commit_callbacks):
    job = TrainingJob.objects.create(project=project, status="queued", backend="argo", name="logging")
    monkeypatch.setattr(
        "apps.training.tasks.training_backend", lambda _: SimpleNamespace(run=lambda _: {"dispatched": True})
    )
    monkeypatch.setattr(training_logs, "append_training_log", Mock())
    emitted = Mock()
    monkeypatch.setattr(app_logging, "log_event", emitted)
    with django_capture_on_commit_callbacks(execute=True):
        assert execute_training_job.run(str(job.public_id)) == "running"
        emitted.assert_not_called()
    assert [c.args[2] for c in emitted.call_args_list] == ["training_job.running", "training_job.dispatched"]
    job.refresh_from_db()
    assert job.status == "running"
    assert job.completed_at is None


def test_build_webhook_replay_logs_only_first_transition(
    project, settings, monkeypatch, django_capture_on_commit_callbacks
):
    settings.CONTROL_PLANE_WEBHOOK_SECRET = "test-callback-secret"
    build = Build.objects.create(project=project, status="building", flavor="sklearn")
    monkeypatch.setattr("apps.deployment.api.webhooks.cleanup_failed_build_artifacts.delay", Mock())
    emitted = Mock()
    monkeypatch.setattr(app_logging, "log_event", emitted)
    client = APIClient()
    url = f"/internal/webhooks/builds/{build.public_id}/"
    with django_capture_on_commit_callbacks(execute=True):
        first = client.post(
            url,
            {"status": "failed", "error_message": "token=private-error"},
            format="json",
            HTTP_X_CONTROL_PLANE_SECRET=settings.CONTROL_PLANE_WEBHOOK_SECRET,
        )
        second = client.post(
            url, {"status": "success"}, format="json", HTTP_X_CONTROL_PLANE_SECRET=settings.CONTROL_PLANE_WEBHOOK_SECRET
        )
        emitted.assert_not_called()
    assert first.status_code == 200
    assert second.data["duplicate"] is True
    assert emitted.call_count == 1
    assert emitted.call_args.args[2] == "build.failed"
    assert emitted.call_args.kwargs["source"] == "webhook"
    assert "private-error" not in str(emitted.call_args)


@pytest.mark.parametrize("decode", [deployment_logs._decode_logs, training_logs._decode, drift_logs._decode_logs])
def test_runtime_logs_sanitize_secrets_urls_and_bound_lines(decode):
    lines = decode([b"token=private-value", "https://storage.example/private?signature=private-value", "x" * 8000])
    assert "private-value" not in " ".join(lines)
    assert "signature=" not in " ".join(lines)
    assert len(lines) == 3
    assert len(lines[2]) < 2100


@pytest.mark.parametrize("kind", ["build", "training"])
def test_persisted_log_fallback_is_sanitized_without_changing_offset(kind, monkeypatch):
    redis = Mock(lrange=Mock(return_value=[]), llen=Mock(return_value=0))
    monkeypatch.setattr(deployment_logs.Redis, "from_url", lambda _: redis)
    resource = SimpleNamespace(
        public_id=uuid.uuid4(),
        logs="first\ntoken=private-value",
        tracking={"logs_tail": "first\ntoken=private-value"},
        error_message="",
    )
    read = deployment_logs.build_logs if kind == "build" else training_logs.training_logs
    lines, offset = read(resource, 1)
    assert offset == 2
    assert len(lines) == 1
    assert "private-value" not in lines[0]


def test_runtime_writers_sanitize_before_redis(monkeypatch):
    redis = Mock()
    monkeypatch.setattr(training_logs.Redis, "from_url", lambda _: redis)
    training_logs.append_training_log(uuid.uuid4(), "Authorization: Bearer private-value")
    deployment_logs.append_deployment_log(SimpleNamespace(public_id=uuid.uuid4()), "token=private-value")
    assert redis.rpush.call_count == 2
    assert "private-value" not in str(redis.rpush.call_args_list)


def test_gunicorn_uses_local_logging_without_access_handlers(monkeypatch):
    configure = Mock()
    monkeypatch.setattr(gunicorn_conf, "configure_logging", configure)
    logger = logging.getLogger("gunicorn.error")
    monkeypatch.setattr(logger, "handlers", [logging.NullHandler()])
    monkeypatch.setattr(logger, "propagate", False)
    gunicorn_conf.post_fork(None, None)
    configure.assert_called_once_with()
    assert logger.handlers == []
    assert logger.propagate is True
    assert gunicorn_conf.accesslog is None


@pytest.mark.parametrize("handled", [True, False])
def test_task_failure_emits_one_safe_error(handled, monkeypatch):
    emitted = Mock()
    monkeypatch.setattr(celery_logging, "log_event", emitted)
    monkeypatch.setattr(celery_logging, "task_summary", Mock())
    task = SimpleNamespace(name="test.task", request=SimpleNamespace(headers={}))
    celery_logging.task_start(task_id="task-1", task=task)
    try:
        app_logging.failure_reported.set(handled)
        try:
            raise RuntimeError("token=private-error")
        except RuntimeError as exc:
            celery_logging.task_failed(
                sender=task,
                exception=exc,
                traceback=exc.__traceback__,
                args=["private-argument"],
                kwargs={"private": "payload"},
            )
        celery_logging.task_finish(task=task, state="FAILURE")
        errors = [call for call in emitted.call_args_list if call.args[1] == "ERROR"]
        assert len(errors) == (0 if handled else 1)
        if errors:
            from common.logging_utils import JsonFormatter

            fields = dict(errors[0].kwargs)
            record = logging.LogRecord(
                "test", logging.ERROR, __file__, 1, errors[0].args[3], (), fields.pop("exc_info")
            )
            for name, value in fields.items():
                setattr(record, name, value)
            rendered = JsonFormatter("control-plane").format(record)
            assert "RuntimeError" in rendered
            assert "private" not in rendered
    finally:
        if hasattr(task.request, "_logging_token"):
            celery_logging.task_finish(task=task, state="FAILURE")


def test_unsafe_celery_trace_and_duplicate_django_request_are_filtered():
    filter_ = app_logging.FrameworkLogFilter()
    trace = logging.LogRecord(
        "celery.app.trace", logging.ERROR, __file__, 1, "Task failed args=%s", (["private"],), None
    )
    assert filter_.filter(trace) is False
    request = logging.LogRecord("django.request", logging.ERROR, __file__, 1, "Server error", (), None)
    assert filter_.filter(request) is True
    request.request = SimpleNamespace(_mlops_request_logging=True)
    assert filter_.filter(request) is False


def test_http_failures_are_not_suppressed_after_success(caplog):
    middleware = RequestContextMiddleware(lambda req: HttpResponse(status=200 if req.path == "/ok/" else 503))
    with caplog.at_level(logging.INFO):
        for path in ("/fail/", "/ok/", "/fail/"):
            request = RequestFactory().get(path)
            request.resolver_match = ResolverMatch(lambda req: HttpResponse(), (), {}, route=path)
            middleware(request)
    errors = [r for r in caplog.records if getattr(r, "event", "") == "http.request.failed"]
    assert len(errors) == 2


def test_build_task_does_not_repeat_callback_ready(project, monkeypatch, django_capture_on_commit_callbacks):
    build = Build.objects.create(project=project, status="queued", flavor="sklearn")

    def callback_then_return(resource):
        Build.objects.filter(pk=resource.pk).update(status="ready")
        app_logging.record_transition(resource, "ready", source="webhook")
        return "runtime output"

    monkeypatch.setattr("apps.deployment.tasks.build_backend", lambda _: SimpleNamespace(run=callback_then_return))
    emitted = Mock()
    monkeypatch.setattr(app_logging, "log_event", emitted)
    with django_capture_on_commit_callbacks(execute=True):
        assert execute_build.run(str(build.public_id)) == "ready"
    ready = [c for c in emitted.call_args_list if c.args[2] == "build.ready"]
    assert len(ready) == 1
    assert ready[0].kwargs["source"] == "webhook"


def test_django_converted_exception_retains_diagnostic_and_cleans_up(settings, monkeypatch):
    from django.urls import path

    def broken_view(request):
        raise RuntimeError("token=private-view-error")

    settings.ROOT_URLCONF = type("LoggingTestUrls", (), {"urlpatterns": [path("broken/", broken_view)]})
    summary = Mock()
    monkeypatch.setattr("common.middleware.Summary", lambda *_: summary)
    client = APIClient()
    client.raise_request_exception = False
    response = client.get("/broken/")
    assert response.status_code == 500
    summary.failure.assert_called_once()
    fields = summary.failure.call_args.kwargs
    assert fields["error_type"] == "RuntimeError"
    assert fields["exc_info"][0] is RuntimeError
    assert fields["exc_info"][2] is not None
    assert not hasattr(response.wsgi_request, "_mlops_exception")


@pytest.mark.django_db
def test_lifecycle_snapshots_exception_before_commit(monkeypatch, django_capture_on_commit_callbacks):
    emitted = Mock()
    monkeypatch.setattr(app_logging, "log_event", emitted)
    with django_capture_on_commit_callbacks(execute=True):
        try:
            raise RuntimeError("token=private-backend-error")
        except RuntimeError:
            app_logging.lifecycle_event(
                "build.failed",
                resource_type="build",
                resource_id=uuid.uuid4(),
                status="failed",
                exc_info=True,
            )
        emitted.assert_not_called()
    assert emitted.call_args.kwargs["exc_info"][0] is RuntimeError
    assert emitted.call_args.kwargs["exc_info"][2] is not None


@pytest.mark.django_db
def test_drift_summary_backfill_does_not_claim_new_completion(
    monkeypatch, settings, django_capture_on_commit_callbacks
):
    from apps.drift.tests.test_webhook_race_condition import _drift_fixture

    run = _drift_fixture()
    run.status = "completed"
    run.save(update_fields=["status"])
    settings.CONTROL_PLANE_WEBHOOK_SECRET = "test-callback-secret"
    emitted = Mock()
    monkeypatch.setattr(app_logging, "log_event", emitted)
    with django_capture_on_commit_callbacks(execute=True):
        response = APIClient().post(
            f"/internal/webhooks/drift-runs/{run.public_id}/",
            {"summary": {"drift_score": 0.1, "has_drift": False}},
            format="json",
            HTTP_X_CONTROL_PLANE_SECRET=settings.CONTROL_PLANE_WEBHOOK_SECRET,
        )
    assert response.status_code == 200
    assert [call.args[2] for call in emitted.call_args_list] == ["drift_run.summary_updated"]


@pytest.mark.django_db
def test_drift_task_does_not_repeat_callback_completion(monkeypatch, django_capture_on_commit_callbacks):
    from apps.drift.models import DriftRun
    from apps.drift.tasks import execute_drift_run
    from apps.drift.tests.test_webhook_race_condition import _drift_fixture

    run = _drift_fixture()

    def callback_then_return(resource):
        DriftRun.objects.filter(pk=resource.pk).update(status="completed")
        app_logging.record_transition(resource, "completed", source="webhook")
        return "runtime output"

    monkeypatch.setattr("apps.drift.tasks.drift_backend", lambda _: SimpleNamespace(run=callback_then_return))
    emitted = Mock()
    monkeypatch.setattr(app_logging, "log_event", emitted)
    with django_capture_on_commit_callbacks(execute=True):
        assert execute_drift_run.run(str(run.public_id)) == "completed"
    completed = [call for call in emitted.call_args_list if call.args[2] == "drift_run.completed"]
    assert len(completed) == 1
    assert completed[0].kwargs["source"] == "webhook"
