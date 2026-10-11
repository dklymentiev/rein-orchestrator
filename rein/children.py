"""
Rein Children - the scripts a block has started, and how to stop them.

A block's script runs as a child process in a session of its own. Each one is
recorded in `state/children/` of the task, so that it can be stopped as a
whole (the script and whatever it started) by the engine that started it, and
found again by a later engine process if the first one died without cleaning
up. Without this, a script outlives the step that started it and the next step
starts the same block a second time next to it.
"""

import json
import os
import signal
import subprocess
import threading
import time
from typing import Callable, Dict, List, Optional

import psutil

# How long a script gets to exit after SIGTERM before it is killed.
TERM_GRACE_SECONDS = 3.0


def _stop_group(pid: int, wait: Callable[[float], bool]) -> bool:
    """SIGTERM the process group led by pid, then SIGKILL what is left.

    `wait(seconds)` returns True once the leader is gone. Returns False when
    the group could not be signalled (it belongs to another user).
    """
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    if not wait(TERM_GRACE_SECONDS):
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        wait(TERM_GRACE_SECONDS)
    return True


class ChildRegistry:
    """Scripts started for the blocks of one task."""

    def __init__(self, task_dir: str, logger: Optional[Callable[[str], None]] = None):
        self.task_dir = task_dir
        self.dir = os.path.join(task_dir, "state", "children")
        self.logger = logger or (lambda x: None)
        self._lock = threading.Lock()
        self._live: Dict[int, subprocess.Popen] = {}

    def _path(self, pid: int) -> str:
        return os.path.join(self.dir, f"{pid}.json")

    def started(self, block: str, proc: subprocess.Popen) -> None:
        """Record a script that has just been started for a block."""
        try:
            created = psutil.Process(proc.pid).create_time()
        except psutil.Error:
            created = time.time()
        with self._lock:
            self._live[proc.pid] = proc
            try:
                os.makedirs(self.dir, exist_ok=True)
                with open(self._path(proc.pid), "w") as f:
                    json.dump({"block": block or "", "pid": proc.pid, "create_time": created}, f)
            except OSError as e:
                self.logger(f"CHILD RECORD ERROR | {block} | pid={proc.pid} | {e}")

    def finished(self, proc: subprocess.Popen) -> None:
        """Forget a script that has exited."""
        with self._lock:
            self._live.pop(proc.pid, None)
            try:
                os.remove(self._path(proc.pid))
            except OSError:
                pass

    def _records(self) -> List[dict]:
        records = []
        try:
            names = os.listdir(self.dir)
        except OSError:
            return records
        for name in names:
            try:
                with open(os.path.join(self.dir, name)) as f:
                    records.append(json.load(f))
            except (OSError, ValueError):
                continue
        return records

    def _stop(self, record: dict, reason: str) -> bool:
        """Stop one recorded script. Returns True if it was still running."""
        pid = record.get("pid")
        block = record.get("block", "")
        with self._lock:
            proc = self._live.get(pid)

        if proc is not None:
            if proc.poll() is not None:
                return False

            def wait(seconds: float) -> bool:
                try:
                    proc.wait(timeout=seconds)
                    return True
                except subprocess.TimeoutExpired:
                    return False

        else:
            # Started by an engine process that is gone. The pid may have been
            # reused since, so it only counts if it was created at the same time.
            try:
                found = psutil.Process(pid)
                if abs(found.create_time() - record.get("create_time", 0)) > 1.0:
                    raise psutil.NoSuchProcess(pid)
            except (psutil.Error, TypeError, ValueError):
                try:
                    os.remove(self._path(pid))
                except (OSError, TypeError):
                    pass
                return False

            def wait(seconds: float) -> bool:
                try:
                    found.wait(timeout=seconds)
                    return True
                except psutil.TimeoutExpired:
                    return False
                except psutil.Error:
                    return True

        if _stop_group(pid, wait):
            self.logger(f"SCRIPT STOPPED | {block} | pid={pid} | reason={reason}")
        else:
            self.logger(f"SCRIPT STOP FAILED | {block} | pid={pid} | it runs as another user | reason={reason}")
        if proc is None:
            try:
                os.remove(self._path(pid))
            except OSError:
                pass
        return True

    def stop_block(self, block: str, reason: str) -> int:
        """Stop every script of one block. Returns how many were running."""
        return sum(1 for r in self._records() if r.get("block") == block and self._stop(r, reason))

    def stop_all(self, reason: str) -> int:
        """Stop every script of the task. Returns how many were running."""
        return sum(1 for r in self._records() if self._stop(r, reason))

    def stop_orphans(self, reason: str) -> int:
        """Stop scripts left behind by an engine process that is gone.

        Only for a caller that holds the task lock: with the lock held, a
        recorded script that this process did not start has nobody waiting
        for its result.
        """
        with self._lock:
            mine = set(self._live)
        return sum(1 for r in self._records() if r.get("pid") not in mine and self._stop(r, reason))
