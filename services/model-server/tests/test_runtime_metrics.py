from unittest.mock import AsyncMock

import pytest

from src.runtime_metrics import INCREMENT, record_request


@pytest.mark.asyncio
async def test_shared_counter_is_scoped_atomic_and_short_lived():
    client = AsyncMock()
    await record_request(client, "tenant", "project", "version")
    args = client.eval.call_args.args
    assert args[:3] == (INCREMENT, 1, "runtime_requests:tenant:project:version")
    assert len(args[3]) == 32
    assert "HINCRBY" in INCREMENT and "300" in INCREMENT


@pytest.mark.asyncio
async def test_counter_failure_never_changes_prediction():
    await record_request(None, "tenant", "project", "version")
    await record_request(
        AsyncMock(eval=AsyncMock(side_effect=RuntimeError("sensitive"))), "tenant", "project", "version"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [False, True])
async def test_gateway_counts_authorized_ids_even_when_prediction_fails(monkeypatch, failed):
    from fastapi import HTTPException
    from src import api

    client = AsyncMock()
    monkeypatch.setattr(api, "LOCAL_RUNTIME_METRICS_ENABLED", True)
    monkeypatch.setattr(api, "metrics_redis_client", client)
    monkeypatch.setattr(
        api,
        "_predict",
        AsyncMock(side_effect=HTTPException(503, "unavailable")) if failed else AsyncMock(return_value="ok"),
    )
    record = {"tenant_id": "trusted-tenant", "project_id": "trusted-project", "id": "trusted-version"}
    if failed:
        with pytest.raises(HTTPException):
            await api.predict("untrusted-url-id", None, None, None, {"model_record": record})
    else:
        assert await api.predict("untrusted-url-id", None, None, None, {"model_record": record}) == "ok"
    assert client.eval.call_args.args[2] == "runtime_requests:trusted-tenant:trusted-project:trusted-version"
