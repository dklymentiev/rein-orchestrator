"""
Rein Daemon - Background task watcher with WebSocket server.

Monitors agents/tasks/ for pending tasks and executes them.
Broadcasts live updates via WebSocket to connected clients.
"""
import os
import sys
import json
import yaml
import sqlite3
import asyncio
from typing import Set, Dict

from rein.config import DEFAULT_AGENTS_DIR
from rein.log import get_logger

logger = get_logger(__name__)

WS_CLIENTS: Set = set()


def get_tasks_root(agents_dir: str = "") -> str:
    """Get tasks root directory."""
    agents = agents_dir or DEFAULT_AGENTS_DIR
    return os.environ.get("REIN_TASKS_ROOT", os.path.join(agents, "tasks"))


def get_task_state_snapshot(task_id: str, tasks_root: str = "") -> dict:
    """Get current state of a task from rein.db with full block details."""
    if not tasks_root:
        tasks_root = get_tasks_root()

    task_dir = os.path.join(tasks_root, task_id)
    rein_db = os.path.join(task_dir, "state", "rein.db")

    blocks = []
    task_status = "unknown"

    if os.path.exists(rein_db):
        try:
            conn = sqlite3.connect(rein_db)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            for row in cur.execute("""
                SELECT name, status, phase, progress, start_time, updated_at, exit_code
                FROM processes
            """):
                block_info = {
                    "name": row["name"],
                    "status": row["status"],
                    "phase": row["phase"],
                    "progress": row["progress"],
                }

                if row["start_time"]:
                    block_info["started"] = row["start_time"]
                if row["updated_at"]:
                    block_info["updated"] = row["updated_at"]
                    if row["start_time"]:
                        block_info["duration"] = round(row["updated_at"] - row["start_time"], 1)

                output_json = os.path.join(task_dir, row["name"], "outputs", "result.json")
                output_md = os.path.join(task_dir, row["name"], "outputs", "result.md")
                if os.path.exists(output_json):
                    block_info["output_size"] = os.path.getsize(output_json)
                elif os.path.exists(output_md):
                    block_info["output_size"] = os.path.getsize(output_md)

                blocks.append(block_info)

            total = len(blocks)
            done = sum(1 for b in blocks if b["status"] == "done")
            failed = sum(1 for b in blocks if b["status"] == "failed")
            running = sum(1 for b in blocks if b["status"] == "running")

            if total == 0:
                task_status = "pending"
            elif failed > 0:
                task_status = "failed"
            elif done == total:
                task_status = "completed"
            elif running > 0 or done > 0:
                task_status = "running"
            else:
                task_status = "pending"

            conn.close()
        except Exception as e:
            logger.error("[WS] Error reading task state: %s", e)

    return {
        "type": "state",
        "task_id": task_id,
        "status": task_status,
        "total": len(blocks),
        "done": sum(1 for b in blocks if b["status"] == "done"),
        "failed": sum(1 for b in blocks if b["status"] == "failed"),
        "running": sum(1 for b in blocks if b["status"] == "running"),
        "blocks": blocks
    }


def get_running_tasks(tasks_root: str = "") -> list:
    """Find all running tasks."""
    if not tasks_root:
        tasks_root = get_tasks_root()

    running = []
    if os.path.exists(tasks_root):
        for task_id in os.listdir(tasks_root):
            task_dir = os.path.join(tasks_root, task_id)
            rein_db = os.path.join(task_dir, "state", "rein.db")
            if os.path.exists(rein_db):
                try:
                    conn = sqlite3.connect(rein_db)
                    cur = conn.cursor()
                    total = cur.execute("SELECT COUNT(*) FROM processes").fetchone()[0]
                    done = cur.execute("SELECT COUNT(*) FROM processes WHERE status='done'").fetchone()[0]
                    failed = cur.execute("SELECT COUNT(*) FROM processes WHERE status='failed'").fetchone()[0]
                    conn.close()

                    if total > 0 and done < total and failed == 0:
                        running.append(task_id)
                except Exception:
                    pass
    return running


async def ws_broadcast(event: dict):
    """Broadcast event to all connected WebSocket clients."""
    if not WS_CLIENTS:
        return
    message = json.dumps(event)
    disconnected = set()
    for ws in WS_CLIENTS:
        try:
            await ws.send(message)
        except Exception:
            disconnected.add(ws)
    WS_CLIENTS.difference_update(disconnected)


async def ws_handler(websocket):
    """Handle WebSocket connection."""
    WS_CLIENTS.add(websocket)
    remote = websocket.remote_address
    logger.info("[WS] Client connected: %s", remote)
    try:
        await websocket.send(json.dumps({"type": "connected", "message": "Rein Daemon"}))

        for task_id in get_running_tasks():
            snapshot = get_task_state_snapshot(task_id)
            await websocket.send(json.dumps(snapshot))
            logger.info("[WS] Sent state snapshot for %s", task_id)

        async for message in websocket:
            try:
                msg = json.loads(message)
                if msg.get("type") == "subscribe" and msg.get("task_id"):
                    snapshot = get_task_state_snapshot(msg["task_id"])
                    await websocket.send(json.dumps(snapshot))
                    logger.info("[WS] Sent snapshot for subscribed task %s", msg['task_id'])
            except Exception:
                pass
    except Exception as e:
        logger.error("[WS] Client error: %s", e)
    finally:
        WS_CLIENTS.discard(websocket)
        logger.info("[WS] Client disconnected: %s", remote)


async def monitor_subprocess(proc: asyncio.subprocess.Process, task_id: str, log_file: str):
    """Monitor subprocess stdout and broadcast events."""
    with open(log_file, "w") as lf:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break

            line_str = line.decode('utf-8', errors='replace')
            lf.write(line_str)
            lf.flush()

            if "[BLOCK_START]" in line_str:
                parts = line_str.strip().split()
                event = {"type": "block_start", "task_id": task_id}
                for p in parts[1:]:
                    if "=" in p:
                        k, v = p.split("=", 1)
                        event[k] = v
                await ws_broadcast(event)

            elif "[BLOCK_DONE]" in line_str:
                parts = line_str.strip().split()
                event = {"type": "block_done", "task_id": task_id}
                for p in parts[1:]:
                    if "=" in p:
                        k, v = p.split("=", 1)
                        event[k] = v
                await ws_broadcast(event)
                logger.info("[DAEMON] Block done: %s / %s", task_id, event.get('block', '?'))

            elif "[TASK_DONE]" in line_str:
                parts = line_str.strip().split()
                event = {"type": "task_done", "task_id": task_id}
                for p in parts[1:]:
                    if "=" in p:
                        k, v = p.split("=", 1)
                        event[k] = v
                await ws_broadcast(event)


async def run_daemon_async(agents_dir: str, interval: int, max_workflows: int, ws_port: int):
    """Async daemon loop: watch for tasks and execute them."""
    tasks_dir = os.path.join(agents_dir, "tasks")
    active: Dict[str, asyncio.subprocess.Process] = {}
    monitors: Dict[str, asyncio.Task] = {}

    logger.info("[DAEMON] Started (async)")
    logger.info("[DAEMON] Watching: %s", tasks_dir)
    logger.info("[DAEMON] Interval: %ds | Max parallel: %d", interval, max_workflows)
    logger.info("[DAEMON] WebSocket: ws://127.0.0.1:%d", ws_port)

    while True:
        try:
            # Cleanup completed processes
            for task_id in list(active.keys()):
                proc = active[task_id]
                if proc.returncode is not None:
                    status = "completed" if proc.returncode == 0 else f"failed (exit={proc.returncode})"
                    logger.info("[DAEMON] Finished: %s -> %s", task_id, status)
                    del active[task_id]
                    if task_id in monitors:
                        monitors[task_id].cancel()
                        del monitors[task_id]

            # Find and spawn pending tasks
            if os.path.exists(tasks_dir):
                for task_name in sorted(os.listdir(tasks_dir)):
                    if len(active) >= max_workflows:
                        break
                    if task_name in active:
                        continue

                    task_path = os.path.join(tasks_dir, task_name)
                    if not os.path.isdir(task_path):
                        continue

                    status_marker = os.path.join(task_path, "state", "status")
                    task_yaml = os.path.join(task_path, "task.yaml")

                    is_pending = False
                    rein_db = os.path.join(task_path, "state", "rein.db")

                    if os.path.exists(status_marker):
                        try:
                            with open(status_marker) as f:
                                if f.read().strip() == "pending":
                                    is_pending = True
                        except Exception:
                            pass
                    elif not os.path.exists(rein_db) and os.path.exists(task_yaml):
                        is_pending = True

                    if not is_pending:
                        continue

                    flow_name = ""
                    if os.path.exists(task_yaml):
                        try:
                            with open(task_yaml) as f:
                                task_config = yaml.safe_load(f) or {}
                                flow_name = task_config.get("flow", "")
                        except Exception:
                            pass

                    if not flow_name:
                        continue

                    flow_path = os.path.join(agents_dir, "flows", flow_name, f"{flow_name}.yaml")
                    if not os.path.exists(flow_path):
                        logger.warning("[DAEMON] Skip %s: flow not found", task_name)
                        continue

                    if os.path.exists(status_marker):
                        try:
                            os.remove(status_marker)
                        except Exception:
                            pass

                    logger.info("[DAEMON] Spawning: %s (flow=%s)", task_name, flow_name)
                    log_file = os.path.join(task_path, "state", "rein.log")

                    proc = await asyncio.create_subprocess_exec(
                        sys.executable, "-m", "rein", '--run-task', task_name, '--agents-dir', agents_dir,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT
                    )
                    active[task_name] = proc

                    monitor = asyncio.create_task(monitor_subprocess(proc, task_name, log_file))
                    monitors[task_name] = monitor

                    logger.info("[DAEMON] Started: %s (pid=%s)", task_name, proc.pid)

            if active:
                logger.info("[DAEMON] Active: %d/%d - %s", len(active), max_workflows, list(active.keys()))

            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception("[DAEMON] Error: %s", e)
            await asyncio.sleep(interval)

    for task_id, proc in active.items():
        logger.info("[DAEMON] Terminating: %s", task_id)
        proc.terminate()


def run_daemon(agents_dir: str, interval: int = 5, max_workflows: int = 3, ws_port: int = 8765, no_ui: bool = True):
    """
    Run Rein as daemon with WebSocket server.

    Spawns separate subprocess for each workflow (up to max_workflows parallel).
    """
    async def main():
        try:
            import websockets
            ws_server = await websockets.serve(ws_handler, "127.0.0.1", ws_port)
            logger.info("[DAEMON] WebSocket server started on port %d", ws_port)
        except ImportError:
            logger.warning("[DAEMON] WebSocket disabled (pip install websockets)")
            ws_server = None
        except Exception as e:
            logger.error("[DAEMON] WebSocket failed: %s", e)
            ws_server = None

        try:
            await run_daemon_async(agents_dir, interval, max_workflows, ws_port)
        finally:
            if ws_server:
                ws_server.close()
                await ws_server.wait_closed()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[DAEMON] Shutting down...")
