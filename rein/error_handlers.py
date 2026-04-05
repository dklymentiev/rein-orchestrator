"""Error handler execution for blocks and workflows.

Extracted from ProcessManager. Runs logic.error (per-block) and on_error
(global workflow) scripts when blocks fail.

Both handlers receive a JSON context via stdin:
  {block_name, error, task_dir, task_id, flow_name}
"""
import json
import os
import subprocess
from typing import Callable, Optional, Any


def _run_handler_script(
    script_path_rel: str,
    workflow_dir: str,
    error_context: str,
    log_fn: Callable[[str], None],
    run_log: Optional[Any],
    block_name: str,
    handler_kind: str,
    timeout: int = 60,
) -> bool:
    """Run a single handler script and return True on success.

    handler_kind: 'logic.error' or 'on_error' for log messages.
    """
    try:
        # Handler paths are strictly relative to workflow_dir. The previous
        # implementation had an explicit "try as absolute" fallback after a
        # failed relative lookup, AND Python's os.path.join silently does
        # the same thing when its second argument is absolute. An absolute
        # script_path_rel is therefore rejected explicitly so a workflow
        # cannot designate /bin/ls or /tmp/attacker.sh as an error handler
        # (SEC-06).
        if os.path.isabs(script_path_rel):
            log_fn(
                f"ERROR HANDLER REJECTED | {block_name} | {handler_kind} | "
                f"absolute paths are not allowed: {script_path_rel}"
            )
            return False

        script_path = os.path.join(workflow_dir, script_path_rel)
        if not os.path.isfile(script_path):
            log_fn(
                f"ERROR HANDLER REJECTED | {block_name} | {handler_kind} | "
                f"not found relative to workflow_dir: {script_path_rel}"
            )
            return False

        cmd = ["bash", script_path] if script_path.endswith(".sh") else ["python3", script_path]
        result = subprocess.run(
            cmd,
            input=error_context,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workflow_dir,
        )

        if result.returncode == 0:
            log_fn(f"ERROR HANDLER OK | {block_name} | {handler_kind}")
            if run_log:
                run_log.write(f"{handler_kind.upper()} OK", f"script={script_path_rel}")
                if result.stdout:
                    for line in result.stdout.strip().splitlines()[:20]:
                        run_log.write(f"{handler_kind.upper()} STDOUT", line)
            return True
        else:
            log_fn(
                f"ERROR HANDLER FAILED | {block_name} | {handler_kind} | "
                f"exit={result.returncode} | stderr={result.stderr[:200]}"
            )
            if run_log:
                run_log.write(f"{handler_kind.upper()} FAILED", f"exit={result.returncode}")
                if result.stderr:
                    for line in result.stderr.strip().splitlines()[:20]:
                        run_log.write(f"{handler_kind.upper()} STDERR", line)
            return False
    except Exception as handler_err:
        log_fn(f"ERROR HANDLER EXCEPTION | {block_name} | {handler_kind} | {handler_err}")
        if run_log:
            run_log.write(f"{handler_kind.upper()} EXCEPTION", str(handler_err))
        return False


def run_error_handlers(
    block: dict,
    block_name: str,
    error_msg: str,
    workflow_dir: str,
    task_dir: str,
    task_id: str,
    flow_name: str,
    global_on_error: Optional[str],
    log_fn: Callable[[str], None],
    run_log: Optional[Any] = None,
) -> None:
    """Run error handlers: per-block logic.error first, then global on_error.

    Per-block handler runs first. If it succeeds (exit 0), global on_error
    is skipped (block handler already handled the error).
    """
    error_context = json.dumps({
        "block_name": block_name,
        "error": error_msg,
        "task_dir": task_dir,
        "task_id": task_id or "",
        "flow_name": flow_name or "",
    })

    logic_config = block.get("logic", {}) or {}
    error_script = logic_config.get("error") if isinstance(logic_config, dict) else None
    handled = False

    # Priority 1: per-block logic.error
    if error_script:
        log_fn(f"ERROR HANDLER | {block_name} | logic.error={error_script}")
        if run_log:
            run_log.write("LOGIC.ERROR START", f"script={error_script}")
        handled = _run_handler_script(
            error_script, workflow_dir, error_context,
            log_fn, run_log, block_name, "logic.error",
        )

    # Priority 2: global on_error (only if per-block didn't handle it)
    if not handled and global_on_error:
        log_fn(f"ERROR HANDLER | {block_name} | on_error={global_on_error}")
        _run_handler_script(
            global_on_error, workflow_dir, error_context,
            log_fn, None, block_name, "on_error",
        )
