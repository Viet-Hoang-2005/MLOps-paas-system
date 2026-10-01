"""Tests for scripts/create_and_push_secrets_to_aws.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.create_and_push_secrets_to_aws import (
    DEFAULT_VALUES,
    SecretPreparationError,
    generate_strong_password,
    parse_env_content,
    parse_groups,
    prepare_env_content,
    publish,
)


def test_parse_groups():
    assert parse_groups("0") == list(range(1, 11))
    assert parse_groups("2") == [2]
    assert parse_groups("1, 2, 5") == [1, 2, 5]
    assert parse_groups("5 6") == [5, 6]

    with pytest.raises(SecretPreparationError, match="Select at least one"):
        parse_groups("")

    with pytest.raises(SecretPreparationError, match="Group 0.*cannot be combined"):
        parse_groups("0, 1")

    with pytest.raises(SecretPreparationError, match="Invalid group selection"):
        parse_groups("11")


def test_generate_strong_password():
    pwd = generate_strong_password(32)
    assert len(pwd) == 32
    assert any(c.isupper() for c in pwd)
    assert any(c.islower() for c in pwd)
    assert any(c.isdigit() for c in pwd)


def test_prepare_env_content_redis_auto_generates():
    """Group 2 (Redis) must auto-generate REDIS_PASSWORD and REDIS_SENTINEL_PASSWORD if missing."""
    original = "# Redis config\nREDIS_HOST=localhost\n"
    updated, values = prepare_env_content(original, [2], rotate=[], interactive=False)

    assert "REDIS_PASSWORD" in values
    assert "REDIS_SENTINEL_PASSWORD" in values
    assert len(values["REDIS_PASSWORD"]) >= 32
    assert len(values["REDIS_SENTINEL_PASSWORD"]) >= 32
    assert values["REDIS_PASSWORD"] != values["REDIS_SENTINEL_PASSWORD"]
    assert 'REDIS_PASSWORD="' in updated
    assert 'REDIS_SENTINEL_PASSWORD="' in updated
    assert "# Redis config" in updated


def test_prepare_env_content_redis_preserves_existing():
    """Existing non-empty Redis credentials must be kept unless rotated."""
    original = 'REDIS_PASSWORD="existing-pwd"\nREDIS_SENTINEL_PASSWORD="existing-sentinel-pwd"\n'
    updated, values = prepare_env_content(original, [2], rotate=[], interactive=False)

    assert values["REDIS_PASSWORD"] == "existing-pwd"
    assert values["REDIS_SENTINEL_PASSWORD"] == "existing-sentinel-pwd"
    assert updated == original


def test_prepare_env_content_redis_rotation():
    """Rotating redis must regenerate passwords even if already present."""
    original = 'REDIS_PASSWORD="existing-pwd"\nREDIS_SENTINEL_PASSWORD="existing-sentinel-pwd"\n'
    _updated, values = prepare_env_content(
        original, [2], rotate=["redis"], interactive=False
    )

    assert values["REDIS_PASSWORD"] != "existing-pwd"
    assert values["REDIS_SENTINEL_PASSWORD"] != "existing-sentinel-pwd"


def test_prepare_env_content_db_auto_generates_and_defaults():
    """Group 1 (PostgreSQL) defaults DB_USER and auto-generates DB_PASSWORD."""
    original = "DB_USER=\nDB_PASSWORD=\n"
    updated, values = prepare_env_content(original, [1], rotate=[], interactive=False)

    assert values["DB_USER"] == "postgres"
    assert len(values["DB_PASSWORD"]) >= 32
    assert 'DB_USER="postgres"' in updated


def test_prepare_env_content_control_plane_auto_generates():
    """Group 5 (Control Plane) generates all 5 keys if empty."""
    original = ""
    _updated, values = prepare_env_content(original, [5], rotate=[], interactive=False)

    assert "DJANGO_SECRET_KEY" in values
    assert "JWT_PRIVATE_KEY" in values
    assert "JWT_PUBLIC_KEY" in values
    assert "CONTROL_PLANE_WEBHOOK_SECRET" in values
    assert "ARGO_EVENTS_WEBHOOK_TOKEN" in values


def test_prepare_env_content_missing_external_secret_raises():
    """Non-interactive run missing an external secret like TUNNEL_TOKEN must raise."""
    original = ""
    with pytest.raises(SecretPreparationError, match="Selected groups have missing .env values: TUNNEL_TOKEN"):
        prepare_env_content(original, [4], rotate=[], interactive=False)


def test_prepare_env_content_harbor_hybrid():
    """Group 3 (Harbor) generates strong password in non-interactive mode."""
    original = ""
    _updated, values = prepare_env_content(original, [3], rotate=[], interactive=False)

    assert values["HARBOR_USERNAME"] == DEFAULT_VALUES["HARBOR_USERNAME"]
    assert len(values["HARBOR_PASSWORD"]) >= 24


def test_publish_flow_with_mocked_aws(tmp_path: Path):
    """Test full publish workflow with a mock Secrets Manager client."""
    env_file = tmp_path / ".env"
    env_file.write_text("REDIS_PASSWORD=\nREDIS_SENTINEL_PASSWORD=\n", encoding="utf-8")
    example_file = tmp_path / ".env.example"
    example_file.write_text("", encoding="utf-8")

    mock_client = MagicMock()
    mock_client.describe_secret.return_value = {"ARN": "arn:aws:..."}
    mock_client.get_secret_value.return_value = {"SecretString": "{}"}

    res = publish(
        env_path=env_file,
        example_path=example_file,
        groups=[2],
        rotate=[],
        yes=True,
        interactive=False,
        client=mock_client,
    )

    assert res == 0
    # Check that .env was written and contains the new values
    written_env = env_file.read_text(encoding="utf-8")
    parsed = parse_env_content(written_env)
    assert parsed["REDIS_PASSWORD"]
    assert parsed["REDIS_SENTINEL_PASSWORD"]

    # Check put_secret_value was called on mlops/production-secrets
    mock_client.put_secret_value.assert_called_once()
    call_args = mock_client.put_secret_value.call_args[1]
    assert call_args["SecretId"] == "mlops/production-secrets"
    payload = json.loads(call_args["SecretString"])
    assert payload["REDIS_PASSWORD"] == parsed["REDIS_PASSWORD"]
    assert payload["REDIS_SENTINEL_PASSWORD"] == parsed["REDIS_SENTINEL_PASSWORD"]


def test_rotation_group_mismatch():
    """Rotating redis when only Group 1 (DB) is selected must fail."""
    with pytest.raises(SecretPreparationError, match="Rotation of 'redis' requires"):
        prepare_env_content("", [1], rotate=["redis"], interactive=False)


def test_interactive_external_prompt(monkeypatch):
    """Interactive mode prompts for missing external secrets and saves them."""
    monkeypatch.setattr("getpass.getpass", lambda prompt: "secret-tunnel-token-12345")
    updated, values = prepare_env_content("", [4], rotate=[], interactive=True)
    assert values["TUNNEL_TOKEN"] == "secret-tunnel-token-12345"
    assert 'TUNNEL_TOKEN="secret-tunnel-token-12345"' in updated

