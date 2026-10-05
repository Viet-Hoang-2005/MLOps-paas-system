from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from src.io import post_webhook


def test_retry_uses_identical_payload_and_idempotency_key(monkeypatch):
    sleep = Mock()
    monkeypatch.setattr("src.io.time.sleep", sleep)
    post = Mock(side_effect=[RuntimeError("connection"), SimpleNamespace(status_code=503), SimpleNamespace(status_code=200)])
    payload = {"build_id": "fixture-build", "status": "success", "image_digest": "sha256:fixture"}
    post_webhook("http://callback", payload, SimpleNamespace(post=post), {"X-Control-Plane-Secret": "fixture-secret"})
    assert post.call_count == 3
    assert sleep.call_count == 2
    assert all(call.kwargs["json"] is payload for call in post.call_args_list)
    keys = [call.kwargs["headers"]["Idempotency-Key"] for call in post.call_args_list]
    assert len(set(keys)) == 1
    assert all(call.kwargs["allow_redirects"] is False for call in post.call_args_list)


@pytest.mark.parametrize("code", [400, 401, 403, 409, 302])
def test_permanent_error_does_not_retry_or_leak_payload(monkeypatch, code):
    monkeypatch.setattr("src.io.time.sleep", Mock())
    post = Mock(return_value=SimpleNamespace(status_code=code))
    with pytest.raises(RuntimeError) as error:
        post_webhook("http://callback/private-url", {"build_id": "fixture-build", "private": "private-payload"},
            SimpleNamespace(post=post), {"X-Control-Plane-Secret": "private-header"})
    assert post.call_count == 1
    assert str(error.value) == "Build result callback could not be delivered."
