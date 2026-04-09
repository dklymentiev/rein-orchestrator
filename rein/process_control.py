"""Process control: pause, resume, cancel individual blocks and workflow.

Extracted from ProcessManager. These functions operate on the processes
dict and workflow pause flags, taking them as explicit parameters.
"""

import os
import signal
import time
from typing import Any, Callable, Optional, Tuple


def _find_process(processes: dict, identifier: str) -> Tuple[Optional[str], Optional[Any]]:
    """Look up process by UID first, then by name. Returns (uid, process) or (None, None)."""
    if identifier in processes:
        return identifier, processes[identifier]
    for uid, proc in processes.items():
        if proc.name == identifier:
            return uid, proc
    return None, None


def pause_single(
    processes: dict,
    identifier: str,
    lock,
    state_save: Callable[[Any], None],
    log_fn: Callable[[str], None],
) -> bool:
    """Pause a single process by UID or name."""
    with lock:
        process_id, process = _find_process(processes, identifier)
        if not process:
            return False
        if process.status in ("done", "failed"):
            return False
        if not hasattr(process, "_previous_status"):
            process._previous_status = process.status
        process.status = "paused"

    state_save(process)
    log_fn(f"PAUSE_SINGLE | {process.name}[{process_id}] | previous_status={process._previous_status}")
    return True


def resume_single(
    processes: dict,
    identifier: str,
    lock,
    state_save: Callable[[Any], None],
    log_fn: Callable[[str], None],
) -> bool:
    """Resume a paused process by UID or name."""
    with lock:
        process_id, process = _find_process(processes, identifier)
        if not process:
            return False
        if process.status != "paused":
            return False
        previous = getattr(process, "_previous_status", "waiting")
        process.status = previous
        if hasattr(process, "_previous_status"):
            delattr(process, "_previous_status")

    state_save(process)
    log_fn(f"RESUME_SINGLE | {process.name}[{process_id}] | resumed_to={process.status}")
    return True


def cancel_single(
    processes: dict,
    identifier: str,
    lock,
    state_save: Callable[[Any], None],
    log_fn: Callable[[str], None],
) -> bool:
    """Cancel a single process - kill it and mark as cancelled."""
    with lock:
        process_id, process = _find_process(processes, identifier)
        if not process:
            return False

        # Kill if running
        if process.status == "running" and process.pid:
            try:
                os.kill(process.pid, signal.SIGTERM)
                log_fn(f"KILL SENT | {process.name}[{process_id}] | pid={process.pid}")
            except Exception as e:
                log_fn(f"KILL FAILED | {process.name}[{process_id}] | {str(e)}")

        process.status = "cancelled"
        state_save(process)
        log_fn(f"CANCEL_SINGLE | {process.name}[{process_id}] | previous_status={process.status}")

    return True


def pause_workflow_flags(state: dict, log_fn: Callable[[str], None]) -> bool:
    """Set workflow pause flags. state dict must have 'paused' and 'paused_at' keys.

    Returns False if already paused.
    """
    if state.get("paused"):
        return False
    state["paused"] = True
    state["paused_at"] = time.time()
    log_fn("PAUSE_WORKFLOW | Workflow paused, no new processes will spawn")
    return True


def resume_workflow_flags(state: dict, log_fn: Callable[[str], None]) -> bool:
    """Clear workflow pause flags. Returns False if not paused."""
    if not state.get("paused"):
        return False
    state["paused"] = False
    state["paused_at"] = None
    log_fn("RESUME_WORKFLOW | Workflow resumed, spawning will continue")
    return True
