"""
Rein sweep - enforce time budgets on tasks that nobody is running.

In step mode no process lives between two steps, so a task that waits for an
answer that never comes would wait forever: nothing is there to notice. The
sweep is that something. It walks the tasks directory, finds tasks whose run
or block is over its time budget, and has the engine fail them the same way a
running engine would. It never runs a block.

Run it from anything that ticks: `rein --sweep` from cron or a systemd timer,
or the daemon, which calls it on every loop.
"""

import fcntl
import json
import os
import sqlite3
import time
from typing import Callable, Dict, List, Optional

import yaml

from rein import time_budget as tb

# Task directory names are used as path components; same rule as the daemon.
_SAFE_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def _read_budget_rows(db_path: str) -> Dict[str, tuple]:
    """Read the time_budget table without creating or changing anything."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT name, started_at, expired_at FROM time_budget").fetchall()
    except sqlite3.OperationalError:
        return {}  # a task from before time budgets: nothing recorded yet
    finally:
        conn.close()
    return {name: (started_at, expired_at) for name, started_at, expired_at in rows}


def _over_budget(config: dict, rows: Dict[str, tuple], now: float) -> List[str]:
    """Names over budget and not yet acted on ("" stands for the run)."""
    over = []
    run_row = rows.get(tb.RUN_KEY)
    if run_row and run_row[1]:
        return over  # the run was already stopped for this
    run_seconds = tb.run_budget(config)
    if run_seconds and run_row and now - run_row[0] > run_seconds:
        over.append(tb.RUN_KEY)
    for name, seconds in tb.block_budgets(config.get("blocks", [])).items():
        row = rows.get(name)
        if row and not row[1] and now - row[0] > seconds:
            over.append(name)
    return over


def _held_by_another_process(task_dir: str) -> bool:
    lock_path = os.path.join(task_dir, "state", "rein.lock")
    if not os.path.exists(lock_path):
        return False
    with open(lock_path, "a") as lock_fd:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            return True
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
    return False


def check_task(task_dir: str, agents_dir: str, now: Optional[float] = None) -> str:
    """Check one task. Returns "ok", "busy", "expired" or "skipped".

    Reading comes first and changes nothing. The engine is only brought up
    for a task that is actually over budget, because loading a flow for a
    task touches its state.
    """
    db_path = os.path.join(task_dir, "state", "rein.db")
    if not os.path.exists(db_path):
        return "skipped"  # not started yet

    # `rein --flow` writes input/task.json; a task made for the daemon has task.yaml.
    task_json = os.path.join(task_dir, "input", "task.json")
    task_yaml = os.path.join(task_dir, "task.yaml")
    flow_name, task_input = None, {}
    if os.path.exists(task_json):
        with open(task_json) as f:
            task_data = json.load(f) or {}
        flow_name, task_input = task_data.get("flow"), task_data.get("input", {})
    elif os.path.exists(task_yaml):
        with open(task_yaml) as f:
            flow_name = (yaml.safe_load(f) or {}).get("flow")
    if not flow_name:
        return "skipped"
    flow_path = os.path.join(agents_dir, "flows", flow_name, f"{flow_name}.yaml")
    with open(flow_path) as f:
        config = yaml.safe_load(f) or {}

    rows = _read_budget_rows(db_path)
    if not _over_budget(config, rows, now if now is not None else time.time()):
        return "ok"
    if _held_by_another_process(task_dir):
        return "busy"  # a running engine enforces its own budgets

    # Imported here: the orchestrator pulls in the providers, which a sweep
    # that finds nothing to do never needs.
    from rein.orchestrator import ProcessManager
    from rein.state import ReinState

    manager = ProcessManager(
        max_parallel=config.get("semaphore", 3), flow_name=flow_name, task_input=task_input, agents_dir=agents_dir
    )
    manager.task_id = os.path.basename(task_dir)
    manager.task_dir = task_dir
    manager.run_dir = task_dir
    manager.log_dir = os.path.join(task_dir, "state")
    manager.rein_log_file = os.path.join(task_dir, "state", "rein.log")
    manager.db_path = db_path
    manager.state = ReinState(db_path, resume=True)
    if now is not None:
        manager._now = lambda: now
    manager.load_config(config, workflow_file=flow_path)
    return manager.check_time_budgets()


def sweep(agents_dir: str, log: Callable[[str], None] = print, now: Optional[float] = None) -> Dict[str, list]:
    """Check every task under {agents_dir}/tasks.

    One broken task does not stop the sweep: it is reported under "errors"
    and the rest are still checked.
    """
    result: Dict[str, list] = {"ok": [], "busy": [], "expired": [], "skipped": [], "errors": []}
    tasks_root = os.path.join(agents_dir, "tasks")
    if not os.path.isdir(tasks_root):
        return result

    for task_name in sorted(os.listdir(tasks_root)):
        task_dir = os.path.join(tasks_root, task_name)
        if not os.path.isdir(task_dir) or not set(task_name) <= _SAFE_NAME_CHARS:
            continue
        try:
            outcome = check_task(task_dir, agents_dir, now)
        except BaseException as e:  # SystemExit included: a flow that fails validation must not end the sweep
            if isinstance(e, KeyboardInterrupt):
                raise
            result["errors"].append(task_name)
            log(f"[SWEEP] {task_name}: error: {type(e).__name__}: {e}")
            continue
        result[outcome].append(task_name)
        if outcome == "expired":
            log(f"[SWEEP] {task_name}: over its time budget, failed")
        elif outcome == "busy":
            log(f"[SWEEP] {task_name}: over its time budget, held by a running engine")
    return result
