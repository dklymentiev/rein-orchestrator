"""
Rein Logging - Centralized logging configuration.

Two loggers:
- logger: internal diagnostics -> stderr, format: [REIN] LEVEL: message
- console: CLI user output -> stdout, no prefix/timestamp

Also provides scrub_secrets() — the shared credential redaction function
applied to rein.log, block run logs (runs/run-NNN.log), and the result
field of result.json before persistence (HIGH-003).
"""

import logging
import re
import sys

# Shared credential/token patterns scrubbed from any persisted output.
# Covers provider API keys, bearer tokens, and KEY=VALUE env dumps.
_SECRET_PATTERNS = re.compile(
    r"(sk-[a-zA-Z0-9]{20,}"
    r"|anthropic-[a-zA-Z0-9]{20,}"
    r"|sk-ant-[a-zA-Z0-9_-]{20,}"
    r"|sk-or-[a-zA-Z0-9_-]{20,}"
    r"|ANTHROPIC_API_KEY=[^\s]+"
    r"|OPENAI_API_KEY=[^\s]+"
    r"|OPENROUTER_API_KEY=[^\s]+"
    r"|Bearer\s+[a-zA-Z0-9._-]{20,})"
)


def scrub_secrets(text: str) -> str:
    """Redact API keys, tokens, and credential env assignments from text.

    Applied to all persisted log streams and serialized result data so
    that a leaked task directory does not expose provider credentials
    (HIGH-003). Idempotent and safe on non-string input (returns as-is).
    """
    if not isinstance(text, str):
        return text
    return _SECRET_PATTERNS.sub("[REDACTED]", text)


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
