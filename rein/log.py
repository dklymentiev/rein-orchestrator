"""
Rein Logging - Centralized logging configuration.

Two loggers:
- logger: internal diagnostics -> stderr, format: [REIN] LEVEL: message
- console: CLI user output -> stdout, no prefix/timestamp
"""
import logging
import sys


class _LazyStreamHandler(logging.StreamHandler):
    """StreamHandler that resolves the stream lazily from sys module.

    This ensures pytest capture works correctly, because pytest
    replaces sys.stderr/sys.stdout per-test.
    """

    def __init__(self, stream_attr: str):
        super().__init__()
        self._stream_attr = stream_attr  # "stderr" or "stdout"

    @property
    def stream(self):
        return getattr(sys, self._stream_attr)

    @stream.setter
    def stream(self, value):
        pass  # Ignore; always use current sys stream


def get_logger(name: str = "rein") -> logging.Logger:
    """Get the internal logger ([REIN] prefix, stderr)."""
    log = logging.getLogger(name)
    if not log.handlers:
        handler = _LazyStreamHandler("stderr")
        handler.setFormatter(logging.Formatter("[REIN] %(levelname)s: %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False
    return log


def get_console(name: str = "rein.console") -> logging.Logger:
    """Get the console logger for CLI output (stdout, no timestamp)."""
    log = logging.getLogger(name)
    if not log.handlers:
        handler = _LazyStreamHandler("stdout")
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False
    return log
