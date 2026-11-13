"""Tests for scripts/create_and_push_secrets_to_aws.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from cryptography.fernet import Fernet

from scripts.create_and_push_secrets_to_aws import (
    SecretPreparationError,
    generate_strong_password,
    main,
    parse_env_content,
    parse_groups,
    prepare_env_content,
    publish,
    update_env_content,
)


def test_training_key_generation_preservation_and_validation():
    updated, values = prepare_env_content(
        "# training\nTRAINING_SECRET_ENCRYPTION_KEY=\n", [11], [], interactive=False
    )
    key = values["TRAINING_SECRET_ENCRYPTION_KEY"]
    cipher = Fernet(key.encode())
    assert cipher.decrypt(cipher.encrypt(b"test")) == b"test"
    assert prepare_env_content(updated, [11], [], interactive=False)[0] == updated
    with pytest.raises(SecretPreparationError, match="valid Fernet"):
        prepare_env_content(
            "TRAINING_SECRET_ENCRYPTION_KEY=invalid\n", [11], [], interactive=False
        )


def test_cli_local_and_aws_modes(tmp_path, monkeypatch, capsys):
    path = tmp_path / ".env"
    path.write_text(
        "# keep\nUNRELATED=untouched\nTRAINING_SECRET_ENCRYPTION_KEY=\n",
        encoding="utf-8",
    )
    aws = MagicMock()
    monkeypatch.setattr("scripts.create_and_push_secrets_to_aws.boto3.client", aws)
    args = [
        "--env-file",
        str(path),
        "--keys",
        "TRAINING_SECRET_ENCRYPTION_KEY",
        "--auto",
        "--yes",
        "--non-interactive",
    ]
    assert main(["--mode", "local", *args]) == 0
    aws.assert_not_called()
    values = parse_env_content(path.read_text(encoding="utf-8"))
    assert values["UNRELATED"] == "untouched"
    key = values["TRAINING_SECRET_ENCRYPTION_KEY"]
    client = aws.return_value
    client.get_secret_value.return_value = {"SecretString": '{"OTHER":"keep"}'}
    assert main(["--mode", "aws", *args]) == 0
    payload = json.loads(client.put_secret_value.call_args.kwargs["SecretString"])
    assert payload == {"OTHER": "keep", "TRAINING_SECRET_ENCRYPTION_KEY": key}
    client.put_secret_value.assert_called_once()
    assert key not in capsys.readouterr().out


def test_dry_run_list_and_missing_auto_never_write(tmp_path, monkeypatch, capsys):
    path = tmp_path / ".env"
    original = "TRAINING_SECRET_ENCRYPTION_KEY=\n"
    path.write_text(original, encoding="utf-8")
    aws = MagicMock()
    monkeypatch.setattr("scripts.create_and_push_secrets_to_aws.boto3.client", aws)
    args = [
        "--mode",
        "aws",
        "--env-file",
        str(path),
        "--keys",
        "TRAINING_SECRET_ENCRYPTION_KEY",
        "--non-interactive",
    ]
    assert main([*args, "--auto", "--dry-run"]) == 0
    assert main([*args, "--yes"]) == 1
    assert main(["--env-file", str(path), "--list"]) == 0
    aws.assert_not_called()
    assert path.read_text(encoding="utf-8") == original
    capsys.readouterr()


def test_interactive_manual_training_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr("builtins.input", lambda _: "m")
    monkeypatch.setattr("getpass.getpass", lambda _: key)
    _, values = prepare_env_content("", [11], [], interactive=True, auto=False)
    assert values["TRAINING_SECRET_ENCRYPTION_KEY"] == key


def test_env_round_trip_preserves_sensitive_characters_and_multiline():
    value = "  secret # 'quote' \\\\path ${DO_NOT_EXPAND}  "
    original = '# keep\nTOKEN="old\nmultiline"\nUNRELATED=yes\n'
    updated = update_env_content(original, {"TOKEN": value}, {"TOKEN"})
    assert parse_env_content(updated)["TOKEN"] == value
    assert "old" not in updated and "multiline" not in updated
    assert "# keep" in updated and "UNRELATED=yes" in updated


def test_partial_control_plane_key_selection(tmp_path):
    path = tmp_path / ".env"
    assert (
        main(
            [
                "--mode",
                "local",
                "--env-file",
                str(path),
                "--keys",
                "DJANGO_SECRET_KEY",
                "--auto",
                "--yes",
                "--non-interactive",
            ]
        )
        == 0
    )
    values = parse_env_content(path.read_text(encoding="utf-8"))
    assert values["DJANGO_SECRET_KEY"]
    assert not values.get("JWT_PRIVATE_KEY")
    assert not values.get("ARGO_EVENTS_WEBHOOK_TOKEN")


def test_aws_failure_retains_generated_local_key(tmp_path):
    path = tmp_path / ".env"
    path.write_text("TRAINING_SECRET_ENCRYPTION_KEY=\n", encoding="utf-8")
    client = MagicMock()
    client.get_secret_value.return_value = {"SecretString": "{}"}
    client.put_secret_value.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException"}}, "PutSecretValue"
    )
    with pytest.raises(ClientError):
        publish(
            env_path=path,
            example_path=tmp_path / "example",
            groups=[11],
            rotate=[],
            yes=True,
            interactive=False,
            client=client,
        )
    Fernet(
        parse_env_content(path.read_text(encoding="utf-8"))[
            "TRAINING_SECRET_ENCRYPTION_KEY"
        ].encode()
    )


def test_invalid_aws_json_does_not_write_env(tmp_path):
    path = tmp_path / ".env"
    path.write_text("TRAINING_SECRET_ENCRYPTION_KEY=\n", encoding="utf-8")
    client = MagicMock()
    client.get_secret_value.return_value = {"SecretString": "not json"}
    with pytest.raises(SecretPreparationError, match="invalid JSON"):
        publish(
            env_path=path,
            example_path=path,
            groups=[11],
            rotate=[],
            yes=True,
            interactive=False,
            client=client,
        )
    assert path.read_text(encoding="utf-8") == "TRAINING_SECRET_ENCRYPTION_KEY=\n"
    client.put_secret_value.assert_not_called()


def test_parse_groups():
    assert parse_groups("0") == list(range(1, 12))
    assert parse_groups("2") == [2]
    assert parse_groups("1, 2, 5") == [1, 2, 5]
    assert parse_groups("5 6") == [5, 6]

    with pytest.raises(SecretPreparationError, match="Select at least one"):
        parse_groups("")

    with pytest.raises(SecretPreparationError, match="Group 0.*cannot be combined"):
        parse_groups("0, 1")

    with pytest.raises(SecretPreparationError, match="Invalid group selection"):
        parse_groups("12")


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
    assert "REDIS_PASSWORD=" in updated
    assert 'REDIS_PASSWORD="' not in updated
    assert "REDIS_SENTINEL_PASSWORD=" in updated
    assert 'REDIS_SENTINEL_PASSWORD="' not in updated
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
    assert "DB_USER=postgres" in updated
    assert 'DB_USER="' not in updated


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
    with pytest.raises(
        SecretPreparationError,
        match="Selected groups have missing .env values: TUNNEL_TOKEN",
    ):
        prepare_env_content(original, [4], rotate=[], interactive=False)


def test_harbor_requires_real_provider_credential():
    with pytest.raises(SecretPreparationError, match="HARBOR_PASSWORD"):
        prepare_env_content("", [3], rotate=[], interactive=False)


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
    assert "TUNNEL_TOKEN=secret-tunnel-token-12345" in updated
    assert 'TUNNEL_TOKEN="' not in updated


def test_dynamic_filter_quoted_and_unquoted_newlines():
    """Ensure parse_env_content dynamically filters quotes and normalizes \n newlines."""
    raw = (
        "PLAIN_UNQUOTED=my-secret-value\n"
        'PLAIN_QUOTED="my-quoted-value"\n'
        "NEWLINE_UNQUOTED=header\\nbody\\nfooter\n"
        'NEWLINE_QUOTED="header\\nbody\\nfooter"\n'
    )
    parsed = parse_env_content(raw)
    assert parsed["PLAIN_UNQUOTED"] == "my-secret-value"
    assert parsed["PLAIN_QUOTED"] == "my-quoted-value"
    assert parsed["NEWLINE_UNQUOTED"] == r"header\nbody\nfooter"
    assert parsed["NEWLINE_QUOTED"] == "header\nbody\nfooter"
