#!/usr/bin/env python3
"""
Agent-PM2 ("Dog") - Process Manager with htop-like UI
"""
import os
import sys
import yaml
import json
import sqlite3
import subprocess
import time
import signal
import threading
import re
import uuid
import socket
import select
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Set
from datetime import datetime
from pathlib import Path
import psutil
from rich.console import Console
from rich.table import Table
from rich.live import Live

@dataclass
class Process:
    """Represents a managed process"""
    pid: Optional[int]
    name: str
    status: str  # running, done, failed, waiting, paused
    start_time: float
    command: str
    uid: str = ""  # Unique ID for this process instance (uuid)
    exit_code: Optional[int] = None
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    depends_on: List[str] = field(default_factory=list)
    progress: int = 0  # 0-100
    phase: int = 0  # execution phase number
    blocking_pause: bool = True  # if True, pausing this blocks dependents
    agent: str = ""  # Agent or team executing this process

class DogState:
    """State management with SQLite"""
    def __init__(self, db_path: str = "/tmp/dog.db", resume: bool = False):
        self.db_path = db_path
        self.resume = resume
        self._init_db()

    def _init_db(self):
        """Initialize database schema and clean old data"""
        conn = sqlite3.connect(self.db_path)

        # If resuming, don't drop the table - preserve existing data
        if not self.resume:
            # Drop old table if exists (fresh run)
            conn.execute("DROP TABLE IF EXISTS processes")

        # Create table if it doesn't exist
        conn.execute("""
            CREATE TABLE IF NOT EXISTS processes (
                name TEXT PRIMARY KEY,
                pid INTEGER,
                status TEXT,
                start_time REAL,
                command TEXT,
                exit_code INTEGER,
                cpu_percent REAL,
                memory_mb REAL,
                progress INTEGER,
                phase INTEGER,
                blocking_pause INTEGER,
                updated_at REAL
            )
        """)
        conn.commit()
        conn.close()

    def save_process(self, proc: Process):
        """Save process state"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            REPLACE INTO processes
            (name, pid, status, start_time, command, exit_code, cpu_percent, memory_mb, progress, phase, blocking_pause, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (proc.name, proc.pid, proc.status, proc.start_time, proc.command,
              proc.exit_code, proc.cpu_percent, proc.memory_mb, proc.progress, proc.phase, int(proc.blocking_pause), time.time()))
        conn.commit()
        conn.close()

    def get_all_processes(self) -> List[Process]:
        """Get all tracked processes"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT name, pid, status, start_time, command, exit_code, cpu_percent, memory_mb, progress, phase, blocking_pause FROM processes ORDER BY phase, name"
        ).fetchall()
        conn.close()

        processes = []
        for row in rows:
            proc = Process(
                name=row[0], pid=row[1], status=row[2],
                start_time=row[3], command=row[4],
                exit_code=row[5], cpu_percent=row[6],
                memory_mb=row[7], progress=row[8],
                phase=row[9], blocking_pause=bool(row[10])
            )
            processes.append(proc)
        return processes

class ProcessManager:
    """Manages process execution with semaphore and dependencies"""
    def __init__(self, max_parallel: int = 3, resume_run_id: Optional[str] = None):
        self.max_parallel = max_parallel
        self.guid = None  # Will be set to run_id after directory setup
        self.semaphore = threading.Semaphore(max_parallel)
        self.processes: Dict[str, Process] = {}
        self.running = True
        self.all_blocks = []  # All blocks from config
        self.completed: Set[str] = set()  # Completed block names
        self.lock = threading.Lock()

        # Workflow pause state
        self.workflow_paused = False
        self.workflow_paused_at: Optional[float] = None
        self.resume_run_id = resume_run_id

        # Setup run directory with timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # If resuming, use existing run directory; otherwise create new one
        if resume_run_id:
            self.run_dir = f"/tmp/dog-runs/run-{resume_run_id}"
            self.guid = resume_run_id
        else:
            self.run_dir = f"/tmp/dog-runs/run-{timestamp}"
            self.guid = timestamp

        self.log_dir = os.path.join(self.run_dir, "logs")
        self.dog_log_file = os.path.join(self.run_dir, "dog.log")
        self.db_path = os.path.join(self.run_dir, "dog.db")
        os.makedirs(self.log_dir, exist_ok=True)

        # Initialize state with unique DB for this run (or reuse existing DB if resuming)
        self.state = DogState(self.db_path, resume=bool(resume_run_id))

        # Write metadata
        if resume_run_id:
            # Resuming from previous run - don't create new start_time
            self.metadata = {
                "run_id": resume_run_id,
                "run_dir": self.run_dir,
                "db_path": self.db_path,
                "max_parallel": max_parallel,
                "resumed_at": datetime.now().isoformat()
            }
            self._write_dog_log(f"DOG RESUMED | run_id={resume_run_id} | db={self.db_path}")
        else:
            self.metadata = {
                "start_time": datetime.now().isoformat(),
                "run_id": timestamp,
                "run_dir": self.run_dir,
                "db_path": self.db_path,
                "max_parallel": max_parallel
            }
            self._write_dog_log(f"DOG STARTED | run_id={timestamp} | db={self.db_path} | max_parallel={max_parallel}")

    def _write_dog_log(self, message):
        """Write to dog's own log file"""
        try:
            with open(self.dog_log_file, 'a') as f:
                timestamp = datetime.now().isoformat()
                f.write(f"{timestamp} | {message}\n")
                f.flush()
        except Exception as e:
            print(f"[Dog Log Error] {e}", flush=True)

    def load_config(self, config: dict):
        """Load block configuration"""
        self.all_blocks = config.get('blocks', [])
        self.timeout = config.get('timeout', None)  # timeout in seconds
        self._write_dog_log(f"CONFIG LOADED | {len(self.all_blocks)} blocks | timeout={self.timeout}s")
        self._initialize_all_processes()

        # If resuming, load state from database
        if self.resume_run_id:
            self._load_state_from_db()

    def _load_state_from_db(self):
        """Load workflow state from database when resuming"""
        try:
            # Load all processes from DB
            db_processes = self.state.get_all_processes()

            # Update our in-memory processes with DB state
            for db_proc in db_processes:
                if db_proc.name in self.processes:
                    # Update status and completed set
                    self.processes[db_proc.name].status = db_proc.status
                    self.processes[db_proc.name].exit_code = db_proc.exit_code
                    self.processes[db_proc.name].cpu_percent = db_proc.cpu_percent
                    self.processes[db_proc.name].memory_mb = db_proc.memory_mb
                    self.processes[db_proc.name].progress = db_proc.progress
                    self.processes[db_proc.name].pid = db_proc.pid

                    # Mark completed processes in our tracking set
                    if db_proc.status in ("done", "failed"):
                        self.completed.add(db_proc.name)

            completed_count = len(self.completed)
            self._write_dog_log(f"STATE LOADED | {completed_count}/{len(self.processes)} processes restored from DB")
        except Exception as e:
            self._write_dog_log(f"STATE LOAD ERROR | {str(e)}")

    def _calculate_phase(self, depends_on: List[str], block_phases: Dict[str, int]) -> int:
        """Calculate phase number based on dependencies"""
        if not depends_on:
            return 1
        max_dep_phase = max(block_phases.get(dep, 0) for dep in depends_on) if depends_on else 0
        return max_dep_phase + 1

    def _initialize_all_processes(self):
        """Initialize all processes in DB with 'waiting' status"""
        # First pass - calculate phases
        block_phases: Dict[str, int] = {}
        for block in self.all_blocks:
            name = block['name']
            depends_on = block.get('depends_on', [])
            phase = self._calculate_phase(depends_on, block_phases)
            block_phases[name] = phase

        # Second pass - create processes with phases
        for block in self.all_blocks:
            name = block['name']
            command = block['command']
            depends_on = block.get('depends_on', [])
            phase = block_phases[name]
            blocking_pause = block.get('blocking_pause', True)  # default: True (safer)
            agent = block.get('agent', '')  # Get agent name from config
            uid = str(uuid.uuid4())[:8]  # Short UUID (8 chars)

            process = Process(
                pid=None,
                name=name,
                status="waiting",
                start_time=time.time(),
                command=command,
                uid=uid,  # Add unique ID
                depends_on=depends_on,
                progress=0,
                phase=phase,
                blocking_pause=blocking_pause,
                agent=agent  # Add agent
            )

            with self.lock:
                self.processes[uid] = process  # Use UID as key
            self.state.save_process(process)

    def _find_process_by_name(self, name: str) -> Optional[tuple]:
        """Find process by name, return (uid, process)"""
        with self.lock:
            for uid, proc in self.processes.items():
                if proc.name == name:
                    return (uid, proc)
        return None

    def spawn_process(self, block: dict) -> Optional[Process]:
        """Spawn a new process from block"""
        name = block['name']
        command = block['command']
        depends_on = block.get('depends_on', [])

        # Check if dependencies are met and not blocking-paused
        if depends_on:
            missing = [dep for dep in depends_on if dep not in self.completed]
            if missing:
                return None  # Dependencies not ready

            # Check if any dependency is paused with blocking_pause=True
            with self.lock:
                for uid, proc in self.processes.items():
                    if proc.name in depends_on and proc.status == "paused" and proc.blocking_pause:
                        return None  # Blocked by paused dependency

        self.semaphore.acquire()

        try:
            # Setup environment for agent logging
            env = os.environ.copy()
            env['DOG_LOG_DIR'] = self.log_dir

            proc = subprocess.Popen(
                command, shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env
            )

            # Update existing process with actual PID and running status
            result = self._find_process_by_name(name)
            if not result:
                raise Exception(f"Process {name} not found")

            uid, process = result
            process.pid = proc.pid
            process.status = "running"
            process.start_time = time.time()
            process.progress = 0

            self.state.save_process(process)

            # Log process start with UID and agent
            depends_str = f" | depends_on={process.depends_on}" if process.depends_on else ""
            agent_str = f" | agent={process.agent}" if process.agent else ""
            self._write_dog_log(f"PROCESS STARTED | {name}[{uid}] | pid={proc.pid} | phase={process.phase}{agent_str}{depends_str}")

            # Monitor in background
            threading.Thread(
                target=self._monitor_process,
                args=(uid, proc, process),
                daemon=True
            ).start()

            return process
        except Exception as e:
            print(f"Error spawning {name}: {e}")
            self.semaphore.release()
            return None

    def _monitor_process(self, uid: str, proc: subprocess.Popen, process: Process):
        """Monitor process and collect metrics"""
        name = process.name  # Get name from process object
        try:
            ps_proc = psutil.Process(proc.pid)

            # Thread to read stdout and extract progress from JSON
            def read_output():
                try:
                    if proc.stdout:
                        for line in proc.stdout:
                            try:
                                line = line.decode().strip()
                                # Parse JSON progress lines: [JSON] {...}
                                if line.startswith("[JSON] "):
                                    json_str = line[7:]  # Remove "[JSON] " prefix
                                    data = json.loads(json_str)
                                    if data.get("type") == "progress":
                                        progress = data.get("progress", 0)
                                        process.progress = progress
                                        # Also save to database immediately
                                        self.state.save_process(process)
                            except:
                                pass
                except Exception as e:
                    pass

            output_thread = threading.Thread(target=read_output, daemon=True)
            output_thread.start()

            # Also read stderr to prevent pipe buffer overflow
            def read_errors():
                try:
                    if proc.stderr:
                        for line in proc.stderr:
                            pass  # Discard stderr
                except:
                    pass

            error_thread = threading.Thread(target=read_errors, daemon=True)
            error_thread.start()

            # Wait for process to complete
            while self.running and proc.poll() is None:
                try:
                    process.cpu_percent = ps_proc.cpu_percent(interval=0.1)
                    process.memory_mb = ps_proc.memory_info().rss / 1024 / 1024
                except:
                    pass

                self.state.save_process(process)
                time.sleep(0.25)

            # Process finished - get final status immediately
            exit_code = proc.poll()
            if exit_code is None:
                # Try one more time if poll returned None
                time.sleep(0.1)
                exit_code = proc.poll() or 0

            process.exit_code = exit_code
            process.progress = 100

            # Verify result file (minimal acceptance criteria)
            result_file = os.path.join(self.log_dir, f"{name}.result")
            result_file_exists = os.path.exists(result_file) and os.path.getsize(result_file) > 0

            # Determine final status based on exit code AND result file
            if exit_code == 0 and result_file_exists:
                process.status = "done"
                verification_msg = "result_file_exists"
            elif exit_code != 0 or not result_file_exists:
                process.status = "failed"
                if not result_file_exists:
                    verification_msg = "result_file_missing"
                else:
                    verification_msg = "non_zero_exit"
            else:
                process.status = "done"
                verification_msg = "success"

            # Mark as completed
            with self.lock:
                self.completed.add(name)

            # Final save with status update
            self.state.save_process(process)

            # Log process completion with result verification
            elapsed = time.time() - process.start_time
            self._write_dog_log(f"PROCESS {'COMPLETED' if process.status == 'done' else 'FAILED'} | {name}[{uid}] | pid={process.pid} | exit_code={exit_code} | elapsed={elapsed:.1f}s | verification={verification_msg}")

        except Exception as e:
            # On error, still mark as failed and save
            process.status = "failed"
            with self.lock:
                self.completed.add(name)
            self.state.save_process(process)
            self._write_dog_log(f"PROCESS ERROR | {name}[{uid}] | exception={str(e)}")
        finally:
            self.semaphore.release()

    def run_workflow(self):
        """Execute workflow with dependency management"""
        pending = {block['name']: block for block in self.all_blocks}
        spawned = set()
        loop_count = 0
        start_time = time.time() if self.timeout else None

        while pending or self.processes:
            loop_count += 1

            # Check if timeout exceeded
            if self.timeout and start_time:
                elapsed = time.time() - start_time
                if elapsed > self.timeout:
                    self._write_dog_log(f"TIMEOUT EXCEEDED | elapsed={elapsed:.1f}s > limit={self.timeout}s")
                    self._kill_remaining_processes("timeout exceeded")
                    break

            # Try to spawn ready blocks
            ready = []
            for name, block in pending.items():
                depends_on = block.get('depends_on', [])
                if not depends_on or all(dep in self.completed for dep in depends_on):
                    ready.append(name)

            # Spawn ready blocks (but not if workflow paused, timeout approaching, or semaphore full)
            for name in ready:
                # Check if workflow is paused
                if self.workflow_paused:
                    self._write_dog_log(f"WORKFLOW PAUSED | skipping spawn of {name}")
                    continue

                # Check timeout approaching
                if self.timeout and start_time:
                    elapsed = time.time() - start_time
                    if elapsed > self.timeout * 0.95:  # Don't spawn if 95% timeout used
                        self._write_dog_log(f"TIMEOUT APPROACHING | stopping new spawns at {elapsed:.1f}s")
                        break

                result = self.spawn_process(pending[name])
                if result:
                    spawned.add(name)
                    del pending[name]
                else:
                    # Failed to spawn, might be semaphore issue
                    pass

            # Wait a bit for processes to complete
            time.sleep(0.5)

            # Check if all done (all pending spawned and all processes completed)
            if not pending and self.all_completed():
                break

        # Workflow finished - save summary and stop the UI
        self._finalize_run()
        self.running = False

    def _finalize_run(self):
        """Save metadata and summary after workflow completion"""
        try:
            # Update metadata
            self.metadata["end_time"] = datetime.now().isoformat()
            self.metadata["total_agents"] = len(self.processes)

            # Calculate summary
            completed = sum(1 for p in self.processes.values() if p.status == "done")
            failed = sum(1 for p in self.processes.values() if p.status == "failed")

            summary = {
                "run_id": self.metadata.get("run_id"),
                "start_time": self.metadata.get("start_time"),
                "end_time": self.metadata.get("end_time"),
                "total_agents": len(self.processes),
                "completed": completed,
                "failed": failed,
                "log_dir": self.log_dir
            }

            # Save metadata
            with open(os.path.join(self.run_dir, "metadata.json"), 'w') as f:
                json.dump(self.metadata, f, indent=2)

            # Save summary
            with open(os.path.join(self.run_dir, "summary.json"), 'w') as f:
                json.dump(summary, f, indent=2)

            # Log completion
            self._write_dog_log(f"DOG FINISHED | completed={completed} | failed={failed} | total={len(self.processes)}")

            print(f"\n[OK] Run completed. Logs saved to: {self.run_dir}")
        except Exception as e:
            print(f"[ERROR] Error saving run summary: {e}")
            self._write_dog_log(f"FINALIZE ERROR | {str(e)}")

    def _kill_remaining_processes(self, reason: str = "timeout"):
        """Kill remaining running processes gracefully"""
        with self.lock:
            for name, process in self.processes.items():
                if process.status == "running" and process.pid:
                    try:
                        os.kill(process.pid, signal.SIGTERM)
                        self._write_dog_log(f"SIGTERM SENT | {name} | pid={process.pid} | reason={reason}")
                    except Exception as e:
                        self._write_dog_log(f"KILL FAILED | {name} | {str(e)}")

    def pause_single(self, identifier: str) -> bool:
        """Pause a single process by UID or name"""
        with self.lock:
            # Try to find by UID first, then by name
            process = None
            process_id = identifier

            if identifier in self.processes:
                # Direct UID match
                process = self.processes[identifier]
            else:
                # Try to find by name
                for uid, proc in self.processes.items():
                    if proc.name == identifier:
                        process = proc
                        process_id = uid
                        break

            if not process:
                return False

            # Only pause if not already done/failed
            if process.status in ("done", "failed"):
                return False

            # Store previous status to restore on resume
            if not hasattr(process, '_previous_status'):
                process._previous_status = process.status

            process.status = "paused"

        self.state.save_process(process)
        self._write_dog_log(f"PAUSE_SINGLE | {process.name}[{process_id}] | previous_status={process._previous_status}")
        return True

    def resume_single(self, identifier: str) -> bool:
        """Resume a paused process by UID or name"""
        with self.lock:
            # Try to find by UID first, then by name
            process = None
            process_id = identifier

            if identifier in self.processes:
                # Direct UID match
                process = self.processes[identifier]
            else:
                # Try to find by name
                for uid, proc in self.processes.items():
                    if proc.name == identifier:
                        process = proc
                        process_id = uid
                        break

            if not process:
                return False

            if process.status != "paused":
                return False

            # Restore previous status (running or waiting)
            previous = getattr(process, '_previous_status', 'waiting')
            process.status = previous
            if hasattr(process, '_previous_status'):
                delattr(process, '_previous_status')

        self.state.save_process(process)
        self._write_dog_log(f"RESUME_SINGLE | {process.name}[{process_id}] | resumed_to={process.status}")
        return True

    def cancel_single(self, identifier: str) -> bool:
        """Cancel a single process - kill it and mark as cancelled (won't restart)"""
        with self.lock:
            # Try to find by UID first, then by name
            process = None
            process_id = identifier

            if identifier in self.processes:
                # Direct UID match
                process = self.processes[identifier]
            else:
                # Try to find by name
                for uid, proc in self.processes.items():
                    if proc.name == identifier:
                        process = proc
                        process_id = uid
                        break

            if not process:
                return False

            # Kill process if running
            if process.status == "running" and process.pid:
                try:
                    os.kill(process.pid, signal.SIGTERM)
                    self._write_dog_log(f"KILL SENT | {process.name}[{process_id}] | pid={process.pid}")
                except Exception as e:
                    self._write_dog_log(f"KILL FAILED | {process.name}[{process_id}] | {str(e)}")

            # Mark as cancelled (won't restart on resume)
            process.status = "cancelled"
            self.state.save_process(process)
            self._write_dog_log(f"CANCEL_SINGLE | {process.name}[{process_id}] | previous_status={process.status}")

        return True

    def pause_workflow(self) -> bool:
        """Pause entire workflow - stops spawning new processes"""
        with self.lock:
            if self.workflow_paused:
                return False  # Already paused

            self.workflow_paused = True
            self.workflow_paused_at = time.time()

        self._write_dog_log(f"PAUSE_WORKFLOW | Workflow paused, no new processes will spawn")
        return True

    def resume_workflow(self) -> bool:
        """Resume paused workflow - allows spawning to continue"""
        with self.lock:
            if not self.workflow_paused:
                return False  # Not paused

            self.workflow_paused = False
            self.workflow_paused_at = None

        self._write_dog_log(f"RESUME_WORKFLOW | Workflow resumed, spawning will continue")
        return True

    def all_completed(self) -> bool:
        """Check if all processes are completed"""
        with self.lock:
            return all(p.status in ("done", "failed") for p in self.processes.values())

    def handle_stdin_command(self, cmd: str):
        """Handle stdin commands: pause <uid|name>, resume <uid|name>, cancel <uid|name>, status, log <uid|name>, list, pause-workflow, resume-workflow"""
        cmd = cmd.strip()
        if not cmd:
            return

        parts = cmd.split(maxsplit=1)
        action = parts[0].lower()

        if action == "pause" and len(parts) > 1:
            name = parts[1]
            if self.pause_single(name):
                self._write_dog_log(f"COMMAND | pause {name} | SUCCESS")
            else:
                self._write_dog_log(f"COMMAND | pause {name} | FAILED")

        elif action == "resume" and len(parts) > 1:
            name = parts[1]
            if self.resume_single(name):
                self._write_dog_log(f"COMMAND | resume {name} | SUCCESS")
            else:
                self._write_dog_log(f"COMMAND | resume {name} | FAILED")

        elif action == "pause-workflow":
            if self.pause_workflow():
                self._write_dog_log(f"COMMAND | pause-workflow | SUCCESS")
            else:
                self._write_dog_log(f"COMMAND | pause-workflow | FAILED (already paused)")

        elif action == "resume-workflow":
            if self.resume_workflow():
                self._write_dog_log(f"COMMAND | resume-workflow | SUCCESS")
            else:
                self._write_dog_log(f"COMMAND | resume-workflow | FAILED (not paused)")

        elif action == "status":
            with self.lock:
                running = sum(1 for p in self.processes.values() if p.status == "running")
                paused = sum(1 for p in self.processes.values() if p.status == "paused")
                done = sum(1 for p in self.processes.values() if p.status == "done")
                failed = sum(1 for p in self.processes.values() if p.status == "failed")
                waiting = sum(1 for p in self.processes.values() if p.status == "waiting")
                workflow_paused = "yes" if self.workflow_paused else "no"
            msg = f"COMMAND | status | running={running} paused={paused} done={done} failed={failed} waiting={waiting} workflow_paused={workflow_paused}"
            self._write_dog_log(msg)

        elif action == "log" and len(parts) > 1:
            identifier = parts[1]
            with self.lock:
                # Try to find by UID first, then by name
                process = None
                process_id = identifier

                if identifier in self.processes:
                    process = self.processes[identifier]
                else:
                    for uid, proc in self.processes.items():
                        if proc.name == identifier:
                            process = proc
                            process_id = uid
                            break

                if process:
                    msg = f"COMMAND | log {process.name}[{process_id}] | status={process.status} exit_code={process.exit_code} pid={process.pid} progress={process.progress}"
                    self._write_dog_log(msg)

        elif action == "list":
            # List all processes with their UIDs
            with self.lock:
                for uid, proc in self.processes.items():
                    self._write_dog_log(f"PROCESS | {proc.name}[{uid}] | status={proc.status} pid={proc.pid}")

        elif action == "cancel" and len(parts) > 1:
            identifier = parts[1]
            if self.cancel_single(identifier):
                self._write_dog_log(f"COMMAND | cancel {identifier} | SUCCESS")
            else:
                self._write_dog_log(f"COMMAND | cancel {identifier} | FAILED")

        else:
            self._write_dog_log(f"COMMAND | unknown | {cmd}")

    def start_stdin_reader(self):
        """Start background thread to read stdin commands"""
        def read_stdin():
            try:
                while self.running:
                    try:
                        # Use select for non-blocking read if available (Unix)
                        import select
                        readable, _, _ = select.select([sys.stdin], [], [], 0.5)
                        if readable:
                            cmd = sys.stdin.readline()
                            if cmd:
                                self.handle_stdin_command(cmd)
                    except ImportError:
                        # Fallback: just read with small timeout
                        try:
                            cmd = input()
                            if cmd:
                                self.handle_stdin_command(cmd)
                        except EOFError:
                            break
                        except Exception:
                            pass
            except Exception as e:
                self._write_dog_log(f"STDIN ERROR | {str(e)}")

        thread = threading.Thread(target=read_stdin, daemon=True)
        thread.start()

    def start_socket_server(self, socket_path: Optional[str] = None):
        """Start Unix domain socket server for async command handling"""
        # Use GUID-based socket path if GUID is set
        if socket_path is None:
            if self.guid:
                socket_path = f"/tmp/dog-{self.guid}.sock"
            else:
                socket_path = "/tmp/dog.sock"

        def socket_server():
            # Remove old socket if exists
            try:
                os.unlink(socket_path)
            except FileNotFoundError:
                pass

            try:
                # Create Unix domain socket
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.bind(socket_path)
                sock.listen(5)  # Max 5 pending connections
                sock.setblocking(False)

                self._write_dog_log(f"SOCKET SERVER | listening on {socket_path}")

                clients = []

                try:
                    while self.running:
                        # Non-blocking select with 0.5s timeout (same as stdin)
                        readable, _, _ = select.select([sock] + clients, [], [], 0.5)

                        for s in readable:
                            if s is sock:
                                # New connection
                                try:
                                    client, _ = sock.accept()
                                    client.setblocking(False)
                                    clients.append(client)
                                except Exception as e:
                                    self._write_dog_log(f"SOCKET ACCEPT ERROR | {str(e)}")
                            else:
                                # Data from client
                                try:
                                    data = s.recv(1024).decode().strip()
                                    if data:
                                        # Reuse existing command handler - thread-safe!
                                        self.handle_stdin_command(data)
                                        # Close connection after command (client can send new one)
                                        clients.remove(s)
                                        s.close()
                                    else:
                                        # EOF - close connection
                                        clients.remove(s)
                                        s.close()
                                except Exception as e:
                                    # Connection error - remove client
                                    if s in clients:
                                        clients.remove(s)
                                    try:
                                        s.close()
                                    except:
                                        pass
                finally:
                    # Cleanup on shutdown
                    for client in clients:
                        try:
                            client.close()
                        except:
                            pass
                    sock.close()
                    try:
                        os.unlink(socket_path)
                    except:
                        pass
                    self._write_dog_log(f"SOCKET SERVER | stopped")

            except Exception as e:
                self._write_dog_log(f"SOCKET SERVER ERROR | {str(e)}")

        thread = threading.Thread(target=socket_server, daemon=True, name="SocketServer")
        thread.start()

    def has_work(self) -> bool:
        """Check if there's any work left (processes running or about to run)"""
        with self.lock:
            # If there are running processes, there's work
            if any(p.status == "running" for p in self.processes.values()):
                return True
            # Check if there are processes at all
            if len(self.processes) > 0:
                return True
            # If no processes, workflow thread will handle pending tasks
            return True  # Always return True to keep UI running

class DogUI:
    """htop-like terminal UI using rich"""
    def __init__(self, manager: ProcessManager):
        self.manager = manager
        self.console = Console()

    def calculate_overall_progress(self) -> tuple:
        """Calculate overall progress: (completed_count, total_count, percent)"""
        processes = self.manager.state.get_all_processes()
        if not processes:
            return 0, 0, 0

        total = len(processes)
        completed = sum(1 for p in processes if p.status in ("done", "failed"))

        # Also account for progress of running processes
        running_processes = [p for p in processes if p.status == "running"]
        running_count = len(running_processes)
        running_progress = sum(p.progress for p in running_processes) / max(1, running_count) if running_count > 0 else 0

        # Overall percent = (completed agents * 100 + running agents * their progress) / total
        overall_percent = ((completed * 100) + (running_count * running_progress)) / total

        return completed, total, int(overall_percent)

    def get_time_info(self) -> str:
        """Get elapsed and remaining time"""
        if not self.manager.metadata.get("start_time"):
            return ""

        from datetime import datetime
        start_time = datetime.fromisoformat(self.manager.metadata["start_time"])
        elapsed = int((datetime.now() - start_time).total_seconds())

        # Format elapsed
        elapsed_str = f"{elapsed}s"

        # Calculate remaining if timeout is set
        if self.manager.timeout:
            remaining = max(0, self.manager.timeout - elapsed)
            if remaining > 0:
                remaining_str = f" | [TIMER] {remaining}s remaining"
            else:
                remaining_str = " | [TIMER] TIMEOUT!"
            return f"[TIME] {elapsed_str}{remaining_str}"
        else:
            return f"[TIME] {elapsed_str}"

    def render_table(self) -> Table:
        """Render process table with overall progress"""
        completed, total, percent = self.calculate_overall_progress()
        time_info = self.get_time_info()

        # Create progress bar
        bar_length = 20
        filled = int(bar_length * percent / 100)
        bar = "=" * filled + "-" * (bar_length - filled)
        progress_str = f"[bold blue]{bar}[/bold blue] {percent}% ({completed}/{total})"

        # Add workflow paused indicator if applicable
        workflow_status = " | [red][WORKFLOW PAUSED][/red]" if self.manager.workflow_paused else ""

        # Create main table with time info
        title = f"Dog - Process Monitor - Overall: {progress_str} | {time_info}{workflow_status}"
        table = Table(title=title, show_header=True)
        table.add_column("PID", style="cyan", width=8)
        table.add_column("Name", style="magenta", width=18)
        table.add_column("Agent", style="bright_white", width=12)
        table.add_column("Status", style="green", width=10)
        table.add_column("Progress", style="blue", width=20)
        table.add_column("CPU%", style="yellow", width=6)
        table.add_column("MEM(MB)", style="yellow", width=8)
        table.add_column("Time(s)", style="blue", width=6)

        processes = self.manager.state.get_all_processes()
        for proc in processes:
            if proc.start_time:
                elapsed = time.time() - proc.start_time
            else:
                elapsed = 0

            # Style status based on state
            status_styles = {
                "running": "[yellow]running[/yellow]",
                "done": "[green]done[/green]",
                "failed": "[red]failed[/red]",
                "waiting": "[dim]waiting[/dim]",
                "paused": "[cyan][PAUSED][/cyan]"
            }
            status_text = status_styles.get(proc.status, proc.status)

            # Create ASCII progress bar (only for non-waiting/non-paused processes)
            if proc.status in ("waiting", "paused"):
                progress_str = "-"
                cpu_str = "-"
                mem_str = "-"
                time_str = "-"
            else:
                progress = proc.progress
                bar_length = 10
                filled = int(bar_length * progress / 100)
                bar = "=" * filled + "-" * (bar_length - filled)
                progress_str = f"{bar} {progress}%"
                cpu_str = f"{proc.cpu_percent:.1f}"
                mem_str = f"{proc.memory_mb:.1f}"
                time_str = f"{elapsed:.0f}"

            # Display name with UID
            name_with_uid = f"{proc.name}\n[dim]{proc.uid}[/dim]" if proc.uid else proc.name

            # Display agent if present
            agent_text = proc.agent if proc.agent else "-"

            table.add_row(
                str(proc.pid) if proc.pid else "-",
                name_with_uid,
                agent_text,
                status_text,
                progress_str,
                cpu_str,
                mem_str,
                time_str
            )

        return table

    def run_live(self):
        """Run live monitoring"""
        with Live(self.render_table(), console=self.console, refresh_per_second=4) as live:
            try:
                while self.manager.running:
                    live.update(self.render_table())
                    time.sleep(0.25)
            except KeyboardInterrupt:
                self.console.print("\n[red]Stopped[/red]")
                self.manager.running = False

def load_config(config_path: str) -> dict:
    """Load YAML config"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Dog - Process Manager with htop-like UI')
    parser.add_argument('config', help='Path to YAML configuration file')
    parser.add_argument('--pause', action='store_true', help='Start workflow in paused state')
    parser.add_argument('--resume', metavar='RUN_ID', help='Resume from previous run (RUN_ID like 20251230-142345)')

    args = parser.parse_args()

    config = load_config(args.config)

    # Create manager - GUID will be auto-generated from timestamp or resume_run_id
    manager = ProcessManager(
        max_parallel=config.get('semaphore', 3),
        resume_run_id=args.resume
    )
    manager.load_config(config)

    # Pause workflow if --pause flag provided
    if args.pause:
        manager.pause_workflow()
        print("[PAUSE] Workflow started in paused state")

    # Print run info
    print(f"\n[DIR] Run Directory: {manager.run_dir}")
    print(f"[DB] Database: {manager.db_path}")
    print(f"[LOGS] Logs: {manager.log_dir}")
    if 'start_time' in manager.metadata:
        print(f"[TIMER] Start Time: {manager.metadata['start_time']}")
    elif 'resumed_at' in manager.metadata:
        print(f"[TIMER] Resumed At: {manager.metadata['resumed_at']}")
    if manager.timeout:
        print(f"[TIMEOUT] Timeout: {manager.timeout}s")
    if args.resume:
        print(f"[RESUME] Continuing from run: {args.resume}")
    print()

    # Setup graceful shutdown handler
    def signal_handler(signum, frame):
        print("\n\n[SHUTDOWN] Graceful shutdown initiated...")
        manager._write_dog_log("SIGINT RECEIVED | graceful shutdown")
        manager._kill_remaining_processes("user interrupt")
        manager.running = False
        time.sleep(2)  # Wait for processes to finish
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Start stdin reader for pause/resume commands
    manager.start_stdin_reader()

    # Start Unix domain socket server for async commands
    manager.start_socket_server()

    # Run workflow in background
    workflow_thread = threading.Thread(target=manager.run_workflow, daemon=True)
    workflow_thread.start()

    # Run UI
    ui = DogUI(manager)
    ui.run_live()

    # Exit when done
    manager.running = False
    sys.exit(0)

if __name__ == "__main__":
    main()
