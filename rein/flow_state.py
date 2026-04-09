"""
Rein Flow State - Build complete workflow state as JSON.

Returns blocks with layout coordinates, edges, events, and status.
Used by MCP tools, CLI, and external APIs (HQ dashboard).
"""

import json
import os
import sqlite3

import yaml


def get_flow_state(task_dir: str, agents_dir: str = None) -> dict:
    """Build complete flow state from task directory.

    Args:
        task_dir: Path to task directory (e.g. /agents/tasks/task-20260402-170000)
        agents_dir: Path to agents directory (for loading workflow YAML)

    Returns:
        {flow, status, blocks[], edges[], events[], progress}
    """
    task_dir = os.path.realpath(task_dir)

    if not os.path.isdir(task_dir):
        return {"error": f"Task directory not found: {task_dir}"}

    result = {
        "task_dir": task_dir,
        "task_id": os.path.basename(task_dir),
    }

    # 1. Read task metadata
    task_json_path = os.path.join(task_dir, "input", "task.json")
    if os.path.exists(task_json_path):
        with open(task_json_path) as f:
            task_data = json.load(f)
        result["flow"] = task_data.get("flow", "")
        result["created"] = task_data.get("created", "")
        result["input"] = task_data.get("input", {})
    else:
        # Try task.yaml (older format)
        task_yaml_path = os.path.join(task_dir, "task.yaml")
        if os.path.exists(task_yaml_path):
            with open(task_yaml_path) as f:
                task_data = yaml.safe_load(f) or {}
            result["flow"] = task_data.get("flow", "")
            result["created"] = task_data.get("created_at", "")

    # 2. Load workflow YAML for block metadata (deps, specialist, agent)
    flow_blocks = {}
    flow_name = result.get("flow", "")
    if flow_name and agents_dir:
        flow_yaml = os.path.join(agents_dir, "flows", flow_name, f"{flow_name}.yaml")
        if os.path.exists(flow_yaml):
            with open(flow_yaml) as f:
                flow_config = yaml.safe_load(f) or {}
            for block in flow_config.get("blocks", []):
                name = block.get("name", "")
                flow_blocks[name] = block

    # 3. Read block states from SQLite
    rein_db = os.path.join(task_dir, "state", "rein.db")
    db_blocks = {}
    if os.path.exists(rein_db):
        try:
            conn = sqlite3.connect(rein_db)
            conn.row_factory = sqlite3.Row
            for row in conn.execute(
                "SELECT name, status, phase, progress, start_time, "
                "updated_at, exit_code, run_count FROM processes ORDER BY phase, name"
            ):
                db_blocks[row["name"]] = dict(row)
            conn.close()
        except Exception:
            pass

    # 4. Build blocks list with layout coordinates
    blocks = []
    phase_counts = {}  # phase -> count (for x coordinate)
    edges = []

    for name, db in db_blocks.items():
        phase = db.get("phase", 1)
        phase_counts[phase] = phase_counts.get(phase, 0)
        x_pos = phase_counts[phase]
        phase_counts[phase] += 1

        flow_block = flow_blocks.get(name, {})

        block_info = {
            "name": name,
            "status": db.get("status", "waiting"),
            "phase": phase,
            "progress": db.get("progress", 0),
            "run_count": db.get("run_count", 0),
            "exit_code": db.get("exit_code"),
            "specialist": flow_block.get("specialist", ""),
            "agent": flow_block.get("agent", ""),
            "depends_on": flow_block.get("depends_on", []),
            "x": x_pos,
            "y": phase - 1,
        }

        # Duration
        start = db.get("start_time", 0)
        updated = db.get("updated_at", 0)
        if start and updated and db.get("status") in ("done", "failed"):
            block_info["duration_sec"] = round(updated - start, 1)

        blocks.append(block_info)

        # Build edges from depends_on
        for dep in flow_block.get("depends_on", []):
            edges.append({"from": dep, "to": name})

    # 5. Compute overall status
    total = len(blocks)
    done = sum(1 for b in blocks if b["status"] == "done")
    failed = sum(1 for b in blocks if b["status"] == "failed")
    running = sum(1 for b in blocks if b["status"] == "running")

    if total == 0:
        status = "pending"
    elif done + failed == total:
        status = "completed" if failed == 0 else "failed"
    elif running > 0 or done > 0:
        status = "running"
    else:
        status = "pending"

    result["status"] = status
    result["blocks"] = blocks
    result["edges"] = edges
    result["progress"] = {
        "total": total,
        "done": done,
        "failed": failed,
        "running": running,
        "waiting": total - done - failed - running,
    }

    # 6. Recent events from rein.log (last 50)
    events = _parse_recent_events(task_dir, limit=50)
    result["events"] = events

    return result


def _parse_recent_events(task_dir: str, limit: int = 50) -> list:
    """Parse recent events from rein.log."""
    log_path = os.path.join(task_dir, "state", "rein.log")
    if not os.path.exists(log_path):
        return []

    events = []
    try:
        with open(log_path) as f:
            lines = f.readlines()

        for line in lines[-limit * 2 :]:  # Read extra to filter
            line = line.strip()
            if not line or " | " not in line:
                continue

            parts = line.split(" | ")
            if len(parts) < 2:
                continue

            ts = parts[0]
            full_rest = " | ".join(parts[1:])

            # Categorize event type
            event_type = "info"
            block_name = ""

            if "BLOCK STARTED" in full_rest or "BLOCK_START" in full_rest:
                event_type = "block.started"
                block_name = _extract_block_name(full_rest)
            elif "BLOCK COMPLETED" in full_rest or "BLOCK_DONE" in full_rest:
                event_type = "block.completed"
                block_name = _extract_block_name(full_rest)
            elif "BLOCK FAILED" in full_rest:
                event_type = "block.failed"
                block_name = _extract_block_name(full_rest)
            elif "STEP MODE" in full_rest:
                event_type = "step.start"
            elif "STEP COMPLETE" in full_rest:
                event_type = "step.complete"
            elif "STEP YIELDING" in full_rest:
                event_type = "step.yield"
            elif "ROUTING" in full_rest:
                event_type = "routing"
                block_name = _extract_block_name(full_rest)
            elif "ERROR HANDLER" in full_rest:
                event_type = "error.handler"
                block_name = _extract_block_name(full_rest)
            elif "AGENT CONFIG" in full_rest:
                event_type = "agent.config"
                block_name = _extract_block_name(full_rest)
            else:
                continue  # Skip debug/internal lines

            events.append(
                {
                    "ts": ts,
                    "type": event_type,
                    "block": block_name,
                    "detail": full_rest[:200],
                }
            )

    except Exception:
        pass

    return events[-limit:]


def _extract_block_name(text: str) -> str:
    """Extract block name from log line like 'BLOCK STARTED | draft[abc123] | ...'."""
    import re

    # Match pattern: name[uid] where name is alphanumeric+hyphens
    match = re.search(r"\b([a-zA-Z][a-zA-Z0-9_-]*)\[", text)
    if match:
        return match.group(1)

    # Try: "block=name" pattern (from BLOCK_START markers)
    match = re.search(r"block=(\S+)", text)
    if match:
        return match.group(1)

    return ""
