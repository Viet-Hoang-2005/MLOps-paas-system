import json
from unittest.mock import Mock

import pytest
from src import pip_stream
from src.logging_utils import RuntimeLog


def test_pip_output_is_emitted_before_the_stream_finishes(monkeypatch):
    detail, progress = Mock(), Mock()
    monkeypatch.setattr(pip_stream.time, "monotonic", Mock(side_effect=range(1, 100)))
    def chunks():
        yield b"Collecting package\r\n\r  10%\r"
        yield b"  20%\r"
        detail.assert_called_once_with("Collecting package")
        progress.assert_called_once_with("  10%", completed=False)
        yield b"  100%\r\nInstalling collected packages\n"
    pip_stream.consume(chunks(), detail, progress)
    progress.assert_any_call("  100%", completed=True)
    detail.assert_any_call("Installing collected packages")


def test_utf8_and_control_sequences_across_chunks():
    detail, progress = Mock(), Mock()
    raw = "\r\x1b[?25l━━ 100%\r\x1b[2K━━ 100%\x1b[?25h\r\n".encode()
    pip_stream.consume((raw[i:i+1] for i in range(len(raw))), detail, progress)
    progress.assert_any_call("━━ 100%", completed=True)
    detail.assert_not_called()


def test_progress_logs_are_redacted_before_transport():
    writer = Mock(return_value=True)
    runtime = RuntimeLog(Mock(), writer=writer)
    runtime.progress("Downloading Authorization: Bearer fixture-private-token", completed=True)
    payload = writer.call_args.args[0]
    assert payload.startswith("TERMINAL_PROGRESS ")
    assert "fixture-private-token" not in payload
    assert json.loads(payload.removeprefix("TERMINAL_PROGRESS "))["done"] is True


def test_progress_preserves_private_key_redaction_state():
    writer = Mock(return_value=True)
    runtime = RuntimeLog(Mock(), writer=writer)
    runtime.progress("-----BEGIN PRIVATE KEY-----")
    runtime.progress("fixture-private-key-body")
    runtime.progress("-----END PRIVATE KEY-----", completed=True)
    assert "fixture-private-key-body" not in str(writer.call_args_list)


@pytest.mark.parametrize("failed", [False, True])
def test_process_and_stream_cleanup(monkeypatch, failed):
    monkeypatch.setattr(pip_stream, "open_terminal", lambda: (None, None))
    stream = Mock()
    stream.read.side_effect = OSError("read failure") if failed else [b"installed\n", b""]
    stream.read1 = stream.read
    process = Mock(stdout=stream)
    process.wait.return_value = 0
    process.poll.return_value = None
    subprocess = Mock(Popen=Mock(return_value=process))
    if failed:
        with pytest.raises(OSError):
            pip_stream.install([], subprocess_module=subprocess, cwd=".", env={}, detail=Mock(), progress=Mock())
        process.terminate.assert_called_once()
    else:
        assert pip_stream.install([], subprocess_module=subprocess, cwd=".", env={}, detail=Mock(), progress=Mock()) == 0
        process.terminate.assert_not_called()
    stream.close.assert_called_once()
