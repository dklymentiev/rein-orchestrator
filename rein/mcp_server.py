"""
Rein MCP Server - Expose Rein workflows as MCP tools.

Run via stdio (Claude Desktop, Cursor, Claude Code):
    python -m rein.mcp_server

Or via SSE for web clients:
    python -m rein.mcp_server --sse --port 8100

Configure in Claude Desktop (claude_desktop_config.json):
    {
      "mcpServers": {
        "rein": {
          "command": "python",
          "args": ["-m", "rein.mcp_server"],
          "env": {
            "ANTHROPIC_API_KEY": "<YOUR_API_KEY>",
            "REIN_AGENTS_DIR": "/path/to/agents"
          }
        }
      }
    }
"""
import os
import sys
import json
import yaml
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from rein.config import ConfigLoader, DEFAULT_AGENTS_DIR


def _get_agents_dir() -> str:
    return os.environ.get("REIN_AGENTS_DIR", DEFAULT_AGENTS_DIR)


mcp = FastMCP(
    "Rein",
    instructions=(
        "Rein is a workflow orchestrator for multi-agent AI. "
        "Use these tools to list, run, and monitor AI workflows."
    ),
)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_flows(agents_dir: str = "") -> str:
    """List available workflows (flows) with their descriptions and block counts.

    Args:
        agents_dir: Path to agents directory. Uses REIN_AGENTS_DIR env or default if empty.
    """
    agents = agents_dir or _get_agents_dir()
    flows_dir = os.path.join(agents, "flows")

    if not os.path.isdir(flows_dir):
        return json.dumps({"error": f"Flows directory not found: {flows_dir}"})

    flows = []
    for name in sorted(os.listdir(flows_dir)):
        flow_yaml = os.path.join(flows_dir, name, f"{name}.yaml")
        if not os.path.isfile(flow_yaml):
            continue
        try:
            with open(flow_yaml) as f:
                cfg = yaml.safe_load(f) or {}
            # Build inputs summary for callers
            inputs_raw = cfg.get("inputs", {})
            inputs_summary = {}
            if inputs_raw and isinstance(inputs_raw, dict):
                for k, v in inputs_raw.items():
                    if isinstance(v, dict):
                        inputs_summary[k] = {
                            "required": v.get("required", True),
                            "description": v.get("description", ""),
                        }
                        if "default" in v:
                            inputs_summary[k]["default"] = v["default"]
                    else:
                        inputs_summary[k] = {"required": True}

            entry = {
                "name": name,
                "description": cfg.get("description", ""),
                "blocks": len(cfg.get("blocks", [])),
                "team": cfg.get("team", ""),
                "provider": cfg.get("provider", ""),
            }
            if inputs_summary:
                entry["inputs"] = inputs_summary
            flows.append(entry)
        except Exception as e:
            flows.append({"name": name, "error": str(e)})

    return json.dumps({"flows": flows, "agents_dir": agents}, indent=2)


@mcp.tool()
def list_specialists(agents_dir: str = "") -> str:
    """List available AI specialists with the first line of their instructions.

    Args:
        agents_dir: Path to agents directory. Uses REIN_AGENTS_DIR env or default if empty.
    """
    agents = agents_dir or _get_agents_dir()
    spec_dir = os.path.join(agents, "specialists")

    if not os.path.isdir(spec_dir):
        return json.dumps({"error": f"Specialists directory not found: {spec_dir}"})

    specialists = []
    for fname in sorted(os.listdir(spec_dir)):
        if not fname.endswith(".md"):
            continue
        name = fname[:-3]
        try:
            with open(os.path.join(spec_dir, fname)) as f:
                first_line = ""
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        first_line = line[:120]
                        break
            specialists.append({"name": name, "summary": first_line})
        except Exception as e:
            specialists.append({"name": name, "error": str(e)})

    return json.dumps({"specialists": specialists, "count": len(specialists)}, indent=2)


@mcp.tool()
def list_teams(agents_dir: str = "") -> str:
    """List available teams and their specialist composition.

    Args:
        agents_dir: Path to agents directory. Uses REIN_AGENTS_DIR env or default if empty.
    """
    agents = agents_dir or _get_agents_dir()
    teams_dir = os.path.join(agents, "teams")

    if not os.path.isdir(teams_dir):
        return json.dumps({"error": f"Teams directory not found: {teams_dir}"})

    teams = []
    for fname in sorted(os.listdir(teams_dir)):
        if not fname.endswith(".yaml"):
            continue
        name = fname[:-5]
        try:
            with open(os.path.join(teams_dir, fname)) as f:
                cfg = yaml.safe_load(f) or {}
            teams.append({
                "name": name,
                "description": cfg.get("description", ""),
                "specialists": cfg.get("specialists", []),
            })
        except Exception as e:
            teams.append({"name": name, "error": str(e)})

    return json.dumps({"teams": teams}, indent=2)


@mcp.tool()
def run_workflow(
    workflow_path: str,
    agents_dir: str = "",
    input_json: str = "",
) -> str:
    """Run a Rein workflow and return results.

    Executes the workflow synchronously as a subprocess and returns
    the output when complete. For long-running workflows, use create_task instead.

    Args:
        workflow_path: Path to workflow YAML file.
        agents_dir: Path to agents directory. Uses REIN_AGENTS_DIR env or default if empty.
        input_json: Optional JSON string with input parameters for the workflow.
    """
    if not os.path.isfile(workflow_path):
        return json.dumps({"error": f"Workflow file not found: {workflow_path}"})

    agents = agents_dir or _get_agents_dir()

    cmd = [sys.executable, "-m", "rein", workflow_path, "--agents-dir", agents, "--no-ui"]
    if input_json:
        cmd.extend(["--input", input_json])

    env = {**os.environ, "PYTHONUNBUFFERED": "1"}

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600, env=env
        )

        # Find run directory from output
        run_dir = ""
        for line in result.stdout.splitlines():
            if "[DIR] Run Directory:" in line:
                run_dir = line.split(":", 1)[1].strip()
                break

        # Collect block outputs
        outputs = {}
        if run_dir and os.path.isdir(run_dir):
            for block_name in os.listdir(run_dir):
                output_dir = os.path.join(run_dir, block_name, "outputs")
                if not os.path.isdir(output_dir):
                    continue
                for fname in os.listdir(output_dir):
                    fpath = os.path.join(output_dir, fname)
                    try:
                        with open(fpath) as f:
                            content = f.read()
                        if fname.endswith(".json"):
                            try:
                                content = json.loads(content)
                            except json.JSONDecodeError:
                                pass
                        outputs[f"{block_name}/{fname}"] = content
                    except Exception:
                        pass

        response = {
            "status": "completed" if result.returncode == 0 else "failed",
            "exit_code": result.returncode,
            "outputs": outputs,
        }
        if result.returncode != 0:
            response["stderr"] = result.stderr[-2000:] if result.stderr else ""

        return json.dumps(response, indent=2, default=str)

    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Workflow timed out after 600 seconds"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def create_task(
    flow: str,
    question: str,
    agents_dir: str = "",
    input_json: str = "",
) -> str:
    """Create a new task for the Rein daemon to execute asynchronously.

    The daemon must be running (rein --daemon) to pick up and execute the task.

    Args:
        flow: Name of the flow to run (must exist in agents/flows/).
        question: The question or task description for the workflow.
        agents_dir: Path to agents directory. Uses REIN_AGENTS_DIR env or default if empty.
        input_json: Optional JSON string with structured input parameters for the workflow.
    """
    agents = agents_dir or _get_agents_dir()
    loader = ConfigLoader(agents_dir=agents)

    if not loader.flow_exists(flow):
        return json.dumps({"error": f"Flow not found: {flow}"})

    now = datetime.now(timezone.utc)
    task_id = f"task-{now.strftime('%Y%m%d-%H%M%S')}"
    tasks_root = os.path.join(agents, "tasks")
    task_dir = os.path.join(tasks_root, task_id)

    os.makedirs(os.path.join(task_dir, "input"), exist_ok=True)
    os.makedirs(os.path.join(task_dir, "output"), exist_ok=True)
    os.makedirs(os.path.join(task_dir, "state"), exist_ok=True)

    # task.yaml (daemon reads this)
    task_yaml = {
        "id": task_id,
        "flow": flow,
        "output_dir": "./output",
        "created_at": now.isoformat(),
    }
    with open(os.path.join(task_dir, "task.yaml"), "w") as f:
        yaml.dump(task_yaml, f, default_flow_style=False)

    # question.txt (backward compat - always written)
    with open(os.path.join(task_dir, "input", "question.txt"), "w") as f:
        f.write(question)

    # task.input.json (structured inputs - highest priority in tasks.py loading order)
    if input_json:
        try:
            parsed = json.loads(input_json)
            with open(os.path.join(task_dir, "task.input.json"), "w") as f:
                json.dump(parsed, f, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            return json.dumps({"error": f"Invalid input_json: not valid JSON"})

    # status marker for daemon
    with open(os.path.join(task_dir, "state", "status"), "w") as f:
        f.write("pending")

    return json.dumps({
        "task_id": task_id,
        "flow": flow,
        "status": "pending",
        "task_dir": task_dir,
    }, indent=2)


@mcp.tool()
def task_status(
    task_id: str,
    agents_dir: str = "",
) -> str:
    """Check the status of a task, including block progress and outputs.

    Args:
        task_id: Task ID (e.g. task-20260220-143022).
        agents_dir: Path to agents directory. Uses REIN_AGENTS_DIR env or default if empty.
    """
    agents = agents_dir or _get_agents_dir()
    tasks_root = os.path.join(agents, "tasks")
    task_dir = os.path.join(tasks_root, task_id)

    if not os.path.isdir(task_dir):
        return json.dumps({"error": f"Task not found: {task_id}"})

    result = {"task_id": task_id}

    # Read task.yaml
    task_yaml_path = os.path.join(task_dir, "task.yaml")
    if os.path.exists(task_yaml_path):
        with open(task_yaml_path) as f:
            result["config"] = yaml.safe_load(f) or {}

    # Read status from rein.db
    rein_db = os.path.join(task_dir, "state", "rein.db")
    if os.path.exists(rein_db):
        try:
            conn = sqlite3.connect(rein_db)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            blocks = []
            for row in cur.execute(
                "SELECT name, status, phase, progress, start_time, updated_at, exit_code FROM processes"
            ):
                blocks.append({
                    "name": row["name"],
                    "status": row["status"],
                    "phase": row["phase"],
                    "progress": row["progress"],
                })

            conn.close()

            total = len(blocks)
            done = sum(1 for b in blocks if b["status"] == "done")
            failed = sum(1 for b in blocks if b["status"] == "failed")
            running = sum(1 for b in blocks if b["status"] == "running")

            if total == 0:
                result["status"] = "pending"
            elif failed > 0:
                result["status"] = "failed"
            elif done == total:
                result["status"] = "completed"
            elif running > 0 or done > 0:
                result["status"] = "running"
            else:
                result["status"] = "pending"

            result["blocks"] = blocks
            result["total"] = total
            result["done"] = done
            result["failed"] = failed
            result["running"] = running

        except Exception as e:
            result["db_error"] = str(e)
    else:
        # Check file-based status
        status_path = os.path.join(task_dir, "state", "status")
        if os.path.exists(status_path):
            with open(status_path) as f:
                result["status"] = f.read().strip()
        else:
            result["status"] = "unknown"

    # List outputs
    output_dir = os.path.join(task_dir, "output")
    if os.path.isdir(output_dir):
        outputs = []
        for fname in sorted(os.listdir(output_dir)):
            fpath = os.path.join(output_dir, fname)
            if os.path.isfile(fpath):
                outputs.append({"file": fname, "size": os.path.getsize(fpath)})
        if outputs:
            result["outputs"] = outputs

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def list_tasks(
    agents_dir: str = "",
    limit: int = 20,
) -> str:
    """List recent tasks with their status.

    Args:
        agents_dir: Path to agents directory. Uses REIN_AGENTS_DIR env or default if empty.
        limit: Maximum number of tasks to return (newest first).
    """
    agents = agents_dir or _get_agents_dir()
    tasks_root = os.path.join(agents, "tasks")

    if not os.path.isdir(tasks_root):
        return json.dumps({"tasks": [], "tasks_dir": tasks_root})

    tasks = []
    for task_name in sorted(os.listdir(tasks_root), reverse=True)[:limit]:
        task_dir = os.path.join(tasks_root, task_name)
        if not os.path.isdir(task_dir):
            continue

        entry = {"id": task_name}

        task_yaml_path = os.path.join(task_dir, "task.yaml")
        if os.path.exists(task_yaml_path):
            try:
                with open(task_yaml_path) as f:
                    cfg = yaml.safe_load(f) or {}
                entry["flow"] = cfg.get("flow", "")
                entry["created_at"] = cfg.get("created_at", "")
            except Exception:
                pass

        # Quick status check
        rein_db = os.path.join(task_dir, "state", "rein.db")
        if os.path.exists(rein_db):
            try:
                conn = sqlite3.connect(rein_db)
                cur = conn.cursor()
                total = cur.execute("SELECT COUNT(*) FROM processes").fetchone()[0]
                done = cur.execute("SELECT COUNT(*) FROM processes WHERE status='done'").fetchone()[0]
                failed = cur.execute("SELECT COUNT(*) FROM processes WHERE status='failed'").fetchone()[0]
                conn.close()

                if total == 0:
                    entry["status"] = "pending"
                elif failed > 0:
                    entry["status"] = "failed"
                elif done == total:
                    entry["status"] = "completed"
                else:
                    entry["status"] = "running"
                entry["progress"] = f"{done}/{total}"
            except Exception:
                entry["status"] = "unknown"
        else:
            status_path = os.path.join(task_dir, "state", "status")
            if os.path.exists(status_path):
                try:
                    with open(status_path) as f:
                        entry["status"] = f.read().strip()
                except Exception:
                    entry["status"] = "unknown"
            else:
                entry["status"] = "unknown"

        tasks.append(entry)

    return json.dumps({"tasks": tasks, "count": len(tasks)}, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    transport = "stdio"
    if "--sse" in sys.argv:
        transport = "sse"
    if "--streamable-http" in sys.argv:
        transport = "streamable-http"
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
