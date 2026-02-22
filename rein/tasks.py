"""
Rein Tasks - Task execution helpers.

Functions for executing tasks, saving results to memory, and status management.
"""
import os
import json
import yaml

from rein.state import ReinState


def update_task_status(status_path, status, **kwargs):
    """Legacy status callback. Primary status is tracked in rein.db."""
    pass


def save_task_to_memory(output_dir, memory_config):
    """Save task results to memory system (optional callback)."""
    try:
        if not output_dir or not memory_config:
            return

        result_files = {}
        if os.path.exists(output_dir):
            for fname in os.listdir(output_dir):
                if fname.endswith('.json'):
                    fpath = os.path.join(output_dir, fname)
                    try:
                        with open(fpath) as f:
                            result_files[fname] = json.load(f)
                    except (json.JSONDecodeError, OSError, ValueError):
                        pass

        if not result_files:
            return

        mem_cli = os.environ.get('REIN_MEM_CLI', '')
        if os.path.exists(mem_cli):
            try:
                content = "Task completed with results:\n"
                for fname in sorted(result_files.keys()):
                    content += f"- {fname}\n"

                tags = memory_config.get('tags', [])
                tags_str = ','.join(tags) if tags else 'type:artifact,stage:completed'

                guid = memory_config.get('guid')
                if guid:
                    import subprocess
                    cmd = [mem_cli, 'register', guid, content, tags_str]
                    subprocess.run(cmd, capture_output=True, timeout=10)
                    print(f"[MEMORY] Task results saved to memory")
            except Exception as e:
                print(f"[WARN] Memory callback failed: {e}")
    except Exception as e:
        print(f"[WARN] Error in save_task_to_memory: {e}")


def load_config(config_path: str) -> dict:
    """Load YAML config file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def execute_task(task_id: str, agents_dir: str) -> int:
    """
    Execute a single task (called as subprocess by daemon).

    Returns exit code (0 = success, 1 = failure).
    """
    from rein.orchestrator import ProcessManager

    tasks_dir = os.path.join(agents_dir, "tasks")
    task_path = os.path.join(tasks_dir, task_id)
    task_yaml = os.path.join(task_path, "task.yaml")
    log_file = os.path.join(task_path, "state", "rein.log")
    exit_code_file = os.path.join(task_path, "state", "exit_code")

    # Load flow from task.yaml
    flow_name = ""
    if os.path.exists(task_yaml):
        try:
            with open(task_yaml) as f:
                task_config = yaml.safe_load(f) or {}
                flow_name = task_config.get("flow", "")
        except Exception as e:
            print(f"[ERROR] Cannot read task.yaml: {e}", flush=True)

    if not flow_name:
        print(f"[ERROR] No flow specified in task.yaml", flush=True)
        return 1

    print(f"[TASK] Executing: {task_id}", flush=True)
    print(f"[TASK] Flow: {flow_name}", flush=True)

    flow_path = os.path.join(agents_dir, "flows", flow_name, f"{flow_name}.yaml")
    if not os.path.exists(flow_path):
        print(f"[ERROR] Flow not found: {flow_name}", flush=True)
        return 1

    exit_code = 0
    try:
        config = load_config(flow_path)

        # Setup task input - try multiple formats
        task_input = {}
        task_input_json = os.path.join(task_path, "task.input.json")
        task_json = os.path.join(task_path, "input", "task.json")
        question_txt = os.path.join(task_path, "input", "question.txt")

        if os.path.exists(task_input_json):
            with open(task_input_json) as f:
                task_input = json.load(f)
        elif os.path.exists(task_json):
            with open(task_json) as f:
                task_input = json.load(f)
        elif os.path.exists(question_txt):
            with open(question_txt) as f:
                q = f.read().strip()
                task_input = {"topic": q, "task": q}

        manager = ProcessManager(
            max_parallel=config.get('semaphore', 3),
            flow_name=flow_name,
            task_input=task_input,
            agents_dir=agents_dir
        )

        manager.task_id = task_id
        manager.task_dir = task_path
        manager.run_dir = task_path
        manager.log_dir = os.path.join(task_path, "state")
        manager.rein_log_file = log_file
        manager.db_path = os.path.join(task_path, "state", "rein.db")
        os.makedirs(manager.log_dir, exist_ok=True)
        db_exists = os.path.exists(manager.db_path)
        manager.state = ReinState(manager.db_path, resume=db_exists)

        manager.load_config(config, workflow_file=flow_path)
        manager.run_workflow()
        exit_code = 0

    except Exception as e:
        print(f"[ERROR] {e}", flush=True)
        import traceback
        traceback.print_exc()
        exit_code = 1

    # Write exit code
    os.makedirs(os.path.dirname(exit_code_file), exist_ok=True)
    with open(exit_code_file, "w") as f:
        f.write(str(exit_code))

    status = "completed" if exit_code == 0 else "failed"

    # Count completed blocks
    blocks_completed = 0
    db_path = os.path.join(task_path, "state", "rein.db")
    if os.path.exists(db_path):
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM processes WHERE status='done'")
            blocks_completed = cur.fetchone()[0]
            conn.close()
        except Exception:
            pass

    print(f"[TASK_DONE] task={task_id} status={status} blocks={blocks_completed}", flush=True)
    print(f"[TASK] {task_id}: {status} ({blocks_completed} blocks)", flush=True)
    return exit_code
