"""Read live pip output without buffering a whole installation in memory."""

import codecs
import errno
import os
import re
import time

CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def consume(chunks, detail, progress):
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    text, carriage, replacing = "", False, False
    last_update = 0.0

    def emit(done=False):
        nonlocal last_update
        line = CSI.sub(lambda match: match.group() if match.group().endswith("m") else "", text)
        if not line.strip():
            return
        if replacing:
            if done or time.monotonic() - last_update >= 0.25:
                progress(line, completed=done)
                last_update = time.monotonic()
        else:
            detail(line)

    def characters(value):
        nonlocal text, carriage, replacing
        for char in value:
            if carriage:
                carriage = False
                if char != "\n":
                    replacing = True
                    emit()
                    text = ""
            if char == "\r":
                carriage = True
            elif char == "\n":
                emit(done=True)
                text, replacing = "", False
            else:
                text += char
                if len(text) >= 8192:
                    emit(done=True)
                    text, replacing = "", False

    for chunk in chunks:
        characters(chunk if isinstance(chunk, str) else decoder.decode(chunk))
    characters(decoder.decode(b"", final=True))
    emit(done=True)


def open_terminal():
    if os.name != "posix":
        return None, None
    import fcntl
    import pty
    import struct
    import termios

    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))
    return master, slave


def install(command, *, subprocess_module, cwd, env, detail, progress):
    master = slave = None
    process = None
    finished = False
    try:
        master, slave = open_terminal()
        process = subprocess_module.Popen(
            command, cwd=cwd, env=env, stdin=subprocess_module.DEVNULL,
            stdout=slave if slave is not None else subprocess_module.PIPE,
            stderr=subprocess_module.STDOUT,
        )
        if slave is not None:
            os.close(slave)
            slave = None

        def chunks():
            while True:
                try:
                    chunk = os.read(master, 4096) if master is not None else getattr(process.stdout, "read1", process.stdout.read)(4096)
                except OSError as exc:
                    if master is not None and exc.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    break
                yield chunk

        consume(chunks(), detail, progress)
        code = process.wait()
        finished = True
        return code
    finally:
        for fd in (slave, master):
            if fd is not None:
                os.close(fd)
        if process is not None:
            if process.stdout is not None:
                process.stdout.close()
            if not finished and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess_module.TimeoutExpired:
                    process.kill()
                    process.wait()
