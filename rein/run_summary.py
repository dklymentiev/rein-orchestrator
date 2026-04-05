"""Run finalization: save metadata, summary, update task status.

Extracted from ProcessManager._finalize_run. Side-effectful functions that
write JSON files, update task status files, and copy outputs.
"""
import json
import os
import shutil
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


def build_summary(
    metadata: Dict[str, Any],
    processes: Dict[str, Any],
    log_dir: str,
    total_usage: Any,
    block_usage: Dict[str, Any],
) -> Dict[str, Any]:
    """Build run summary dict from process states and usage tracking."""
    metadata["end_time"] = datetime.now().isoformat()
    metadata["total_agents"] = len(processes)

    completed = sum(1 for p in processes.values() if p.status == "done")
    failed = sum(1 for p in processes.values() if p.status == "failed")

    summary = {
        "run_id": metadata.get("run_id"),
        "start_time": metadata.get("start_time"),
        "end_time": metadata.get("end_time"),
        "total_agents": len(processes),
        "completed": completed,
        "failed": failed,
        "log_dir": log_dir,
    }

    # Per-block stats
    block_stats = {}
    for uid, proc in processes.items():
        block_stats[proc.name] = {
            "status": proc.status,
            "runs": proc.run_count + 1,  # run_count is 0-indexed
            "phase": proc.phase,
            "duration_sec": round(time.time() - proc.start_time, 1) if proc.start_time else 0,
        }
    summary["blocks"] = block_stats

    # Usage/cost
    if total_usage.total_tokens > 0:
        summary["usage"] = total_usage.to_dict()
        summary["block_usage"] = {
            name: u.to_dict() for name, u in block_usage.items()
        }

    return summary


def write_summary_files(
    run_dir: str,
    metadata: Dict[str, Any],
    summary: Dict[str, Any],
) -> None:
    """Persist metadata.json and summary.json to run_dir."""
    with open(os.path.join(run_dir, "metadata.json"), 'w') as f:
        json.dump(metadata, f, indent=2)
    with open(os.path.join(run_dir, "summary.json"), 'w') as f:
        json.dump(summary, f, indent=2)


def update_task_status_file(
    task_dir: str,
    completed: int,
    failed: int,
    total: int,
    log_fn: Callable[[str], None],
    task_id: Optional[str] = None,
) -> None:
    """Update state/status and input/task.json files."""
    status = "completed" if failed == 0 else "failed"

    state_dir = os.path.join(task_dir, "state")
    os.makedirs(state_dir, exist_ok=True)
    with open(os.path.join(state_dir, "status"), "w") as f:
        f.write(f"{status}\n")

    task_json_path = os.path.join(task_dir, "input", "task.json")
    if os.path.exists(task_json_path):
        try:
            with open(task_json_path) as f:
                task_data = json.load(f)
            task_data["status"] = status
            task_data["completed"] = datetime.now().isoformat()
            task_data["blocks_completed"] = completed
            task_data["blocks_failed"] = failed
            task_data["blocks_total"] = total
            with open(task_json_path, "w") as f:
                json.dump(task_data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    log_fn(f"TASK STATUS | {task_id or ''} | status={status}")


def copy_workflow_output_files(
    output_dir: str,
    workflow_file: Optional[str],
    log_fn: Callable[[str], None],
) -> None:
    """Copy workflow YAML/JSON/.env files to output_dir."""
    if not output_dir:
        return
    try:
        os.makedirs(output_dir, exist_ok=True)
        workflow_dir = os.path.dirname(workflow_file) if workflow_file else None
        if workflow_dir:
            for f in os.listdir(workflow_dir):
                if f.endswith(('.json', '.yaml', '.env')):
                    src = os.path.join(workflow_dir, f)
                    dst = os.path.join(output_dir, f)
                    if os.path.isfile(src):
                        try:
                            shutil.copy2(src, dst)
                        except (OSError, IOError, shutil.Error):
                            pass
        log_fn(f"OUTPUT SAVED | {output_dir}")
    except Exception as e:
        log_fn(f"OUTPUT SAVE ERROR | {str(e)}")


def format_cost_line(total_usage: Any) -> str:
    """Format total cost/usage summary line for logging."""
    return (
        f"[COST] Total: ${total_usage.cost:.4f} | "
        f"Tokens: {total_usage.total_tokens:,} "
        f"(in:{total_usage.input_tokens:,} out:{total_usage.output_tokens:,}) | "
        f"Provider: {total_usage.provider} | Model: {total_usage.model}"
    )
