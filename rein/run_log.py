"""
Rein Run Logger - Per-block per-run structured log files.

Each block execution creates a log at:
  task_dir/{block_name}/runs/run-{NNN}.log

Where NNN is the zero-padded run_count (supports revision loops).

All lines are passed through scrub_secrets() so leaked run logs never
expose provider API keys or bearer tokens (HIGH-003).
"""
import os
from datetime import datetime

from rein.log import scrub_secrets


class RunLogger:
    """Structured log writer for a single block execution run."""

    def __init__(self, task_dir: str, block_name: str, run_count: int):
        self.block_name = block_name
        self.run_count = run_count

        runs_dir = os.path.join(task_dir, block_name, "runs")
        os.makedirs(runs_dir, exist_ok=True)

        self.log_path = os.path.join(runs_dir, f"run-{run_count:03d}.log")
        self._fd = open(self.log_path, "w")

    def write(self, category: str, message: str):
        """Write a structured log line: TIMESTAMP | CATEGORY | message

        Message is scrubbed for API keys / bearer tokens before write
        (HIGH-003).
        """
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        safe_message = scrub_secrets(str(message))
        line = f"{ts} | {category} | {safe_message}\n"
        self._fd.write(line)
        self._fd.flush()

    def close(self):
        """Close the log file."""
        if self._fd and not self._fd.closed:
            self._fd.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
