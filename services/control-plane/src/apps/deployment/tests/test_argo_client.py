import pytest
from common.api.exceptions import ServiceUnavailable
from django.test import override_settings
from infrastructure.argo import ArgoWebhookClient

TEST_ARGO_TOKEN = "x" * 32
FAILURE_TEST_ARGO_TOKEN = "y" * 32


class Response:
    @staticmethod
    def json():
        return {"accepted": True}


class RecordingHttp:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return Response()


@override_settings(ARGO_EVENTS_WEBHOOK_TOKEN=TEST_ARGO_TOKEN)
def test_argo_webhook_client_always_sends_dedicated_bearer_token():
    http = RecordingHttp()

    response = ArgoWebhookClient(http=http).trigger(
        "http://argo-events/build",
        {"build_id": "test-build"},
        headers={"Authorization": "Bearer attacker-token", "Idempotency-Key": "request-1"},
    )

    assert response == {"accepted": True}
    assert http.calls == [
        (
            "POST",
            "http://argo-events/build",
            {
                "json": {"build_id": "test-build"},
                "headers": {
                    "Authorization": f"Bearer {TEST_ARGO_TOKEN}",
                    "Idempotency-Key": "request-1",
                },
            },
        )
    ]


@override_settings(ARGO_EVENTS_WEBHOOK_TOKEN="")
def test_argo_webhook_client_fails_closed_without_authentication():
    http = RecordingHttp()

    with pytest.raises(ServiceUnavailable, match="authentication is not configured"):
        ArgoWebhookClient(http=http).trigger("http://argo-events/build", {})

    assert http.calls == []


@override_settings(ARGO_EVENTS_WEBHOOK_TOKEN=FAILURE_TEST_ARGO_TOKEN)
def test_argo_webhook_client_does_not_expose_token_when_delivery_fails(caplog):
    class FailingHttp:
        @staticmethod
        def request(_method, _url, **_kwargs):
            raise RuntimeError("delivery failed")

    with pytest.raises(RuntimeError, match="delivery failed") as exc_info:
        ArgoWebhookClient(http=FailingHttp()).trigger("http://argo-events/build", {})

    assert FAILURE_TEST_ARGO_TOKEN not in str(exc_info.value)
    assert FAILURE_TEST_ARGO_TOKEN not in caplog.text
