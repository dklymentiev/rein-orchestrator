#!/usr/bin/env python3
"""
Rein - Workflow Orchestrator with htop-like UI
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
from dataclasses import asdict
from typing import List, Dict, Optional, Set, Any
from datetime import datetime
from pathlib import Path
import psutil
from rich.console import Console
from rich.table import Table
from rich.live import Live

# Import refactored modules
from rein import (
    Process, ClaudeClient, ConfigLoader, LogicRunner, ReinState,
    format_json_as_md, save_readable_output, get_block_dir, get_output_dir
)

# Import validation engine (Phase 1: Schema validation)
try:
    from models.validator import ValidationEngine
    HAS_VALIDATION = True
except ImportError:
    HAS_VALIDATION = False


class ProcessManager:
    """Manages process execution with semaphore and dependencies"""
    def __init__(self, max_parallel: int = 3, resume_run_id: Optional[str] = None,
                 task_id: Optional[str] = None, flow_name: Optional[str] = None,
                 task_input: Optional[dict] = None, agents_dir: Optional[str] = None):
        self.max_parallel = max_parallel
        self.guid = None  # Will be set to run_id after directory setup
        self.semaphore = threading.Semaphore(max_parallel)
        self.processes: Dict[str, Process] = {}
        self.running = True
        self.all_blocks = []  # All blocks from config
        self.completed: Set[str] = set()  # Completed block names
        self.lock = threading.Lock()
        self.workflow_dir = os.getcwd()  # PHASE 2.5: workflow directory for relative logic paths

        # STATE MACHINE: next queue and run counts (Phase 2.5.4)
        self.next_queue: List[tuple] = []  # [(block_name, trigger_data), ...] blocks to run next
        self.run_counts: Dict[str, int] = {}  # Track run counts per block name
        self.block_configs: Dict[str, dict] = {}  # Store block configs by name for re-running

        # Workflow pause state
        self.workflow_paused = False
        self.workflow_paused_at: Optional[float] = None
        self.resume_run_id = resume_run_id

        # Flow control - stop workflow on critical failure
        self.stop_workflow = False
        self.stop_reason = None

        # Agents directory (specialists, teams, flows, tasks)
        self.agents_dir = agents_dir or "/server/agents"

        # Task system
        self.tasks_root = os.path.join(self.agents_dir, "tasks")
        self.task_id = task_id
        self.task_input = task_input or {}
        self.flow_name = flow_name

        # Setup run directory with timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # V3: ALWAYS create task directory structure
        # task_id is optional name, otherwise auto-generated
        if task_id:
            self.task_dir = os.path.join(self.tasks_root, task_id)
            self.guid = task_id
        elif resume_run_id:
            self.task_dir = f"/tmp/rein-runs/run-{resume_run_id}"
            self.guid = resume_run_id
        else:
            self.task_dir = f"/tmp/rein-runs/run-{timestamp}"
            self.guid = timestamp

        self.run_dir = self.task_dir  # V3: run_dir = task_dir always

        # V3: Create all task directories
        self.log_dir = os.path.join(self.run_dir, "logs")
        self.rein_log_file = os.path.join(self.run_dir, "rein.log")
        self.db_path = os.path.join(self.run_dir, "rein.db")
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(os.path.join(self.task_dir, "state"), exist_ok=True)

        # Initialize state with unique DB for this run (or reuse existing DB if resuming)
        self.state = ReinState(self.db_path, resume=bool(resume_run_id))

        # Initialize refactored components
        self.claude_client = ClaudeClient(logger=self._write_rein_log)
        self.config_loader = ConfigLoader(agents_dir=self.agents_dir, logger=self._write_rein_log)

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
            self._write_rein_log(f"REIN RESUMED | run_id={resume_run_id} | db={self.db_path}")
        else:
            self.metadata = {
                "start_time": datetime.now().isoformat(),
                "run_id": timestamp,
                "run_dir": self.run_dir,
                "db_path": self.db_path,
                "max_parallel": max_parallel
            }
            self._write_rein_log(f"REIN STARTED | run_id={timestamp} | db={self.db_path} | max_parallel={max_parallel}")

    def _write_rein_log(self, message):
        """Write to rein's own log file"""
        try:
            with open(self.rein_log_file, 'a') as f:
                timestamp = datetime.now().isoformat()
                f.write(f"{timestamp} | {message}\n")
                f.flush()
        except Exception as e:
            print(f"[Rein Log Error] {e}", flush=True)

    def create_task(self, flow_name: str, input_params: dict = None) -> str:
        """Create a new task directory and return task_id (v3.0: new structure)"""
        task_id = f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        task_dir = os.path.join(self.tasks_root, task_id)

        # Create task directory structure (v3.0)
        os.makedirs(task_dir, exist_ok=True)
        os.makedirs(os.path.join(task_dir, "input"), exist_ok=True)   # Workflow input
        os.makedirs(os.path.join(task_dir, "output"), exist_ok=True)  # Workflow output
        os.makedirs(os.path.join(task_dir, "state"), exist_ok=True)   # State/logs

        # Write task.json to input/ directory (v3.0)
        task_json = {
            "id": task_id,
            "flow": flow_name,
            "input": input_params or {},
            "created": datetime.now().isoformat(),
            "status": "pending"
        }

        with open(os.path.join(task_dir, "input", "task.json"), "w") as f:
            json.dump(task_json, f, indent=2, ensure_ascii=False)

        # Write initial status file to state/
        with open(os.path.join(task_dir, "state", "status"), "w") as f:
            f.write("pending\n")

        self._write_rein_log(f"TASK CREATED | {task_id} | flow={flow_name} | dir={task_dir}")
        return task_id

    def _get_block_dir(self, block_name: str) -> str:
        """Get/create block directory (delegates to output module)"""
        return get_block_dir(self.task_dir, self.workflow_dir, block_name)

    def _get_output_dir(self, block_name: str = None) -> str:
        """Get output directory (delegates to output module)"""
        return get_output_dir(self.task_dir, self.workflow_dir, block_name)

    def _save_readable_output(self, json_file: str, block_name: str, result: str):
        """Save readable MD output (delegates to output module)"""
        save_readable_output(json_file, block_name, result, self._write_rein_log)

    def _format_json_as_md(self, data: dict, level: int = 0) -> list:
        """Format JSON as markdown (delegates to output module)"""
        return format_json_as_md(data, level)

    def load_config(self, config: dict, workflow_file: str = None):
        """Load block configuration"""
        self.config = config  # Save full config for task mode
        self.workflow_file = workflow_file  # Save workflow file path
        self.all_blocks = config.get('blocks', [])
        self.timeout = config.get('timeout', None)  # timeout in seconds
        self.team_name = config.get('team', None)  # PHASE 2.5: team name

        # Extract workflow directory from file path (for relative logic paths)
        if workflow_file:
            self.workflow_dir = os.path.dirname(os.path.abspath(workflow_file))
        else:
            self.workflow_dir = os.getcwd()

        # Load .env file from flow directory if exists
        self._load_env_file(self.workflow_dir)

        self._write_rein_log(f"CONFIG LOADED | {len(self.all_blocks)} blocks | timeout={self.timeout}s | workflow_dir={self.workflow_dir}")

        # Pre-flight validation (Phase 1: Schema validation)
        if HAS_VALIDATION and workflow_file:
            self._run_preflight_validation(workflow_file)

        self._initialize_all_processes()

        # If resuming, load state from database
        if self.resume_run_id:
            self._load_state_from_db()

    def _run_preflight_validation(self, workflow_file: str):
        """Run schema validation before workflow execution"""
        try:
            engine = ValidationEngine()
            result = engine.validate_workflow(Path(workflow_file), cross_reference_check=True)

            if result.is_valid:
                self._write_rein_log(f"VALIDATE OK | schema_version={result.metadata.get('schema_version')} | blocks={result.metadata.get('blocks_count')} | phases={result.metadata.get('phases')}")
                # Print validation summary to console
                print(f"\n[VALIDATE] Workflow: {result.metadata.get('name')}")
                print(f"[VALIDATE] Team: {result.metadata.get('team')}")
                print(f"[VALIDATE] Schema Version: {result.metadata.get('schema_version')}")
                print(f"[VALIDATE] Blocks: {result.metadata.get('blocks_count')}")
                print(f"[VALIDATE] Execution Phases: {result.metadata.get('phases')}")
                print(f"[VALIDATE] Flow Control Blocks: {result.metadata.get('flow_control_blocks')}")
                print(f"[VALIDATE] Status: OK\n")
            else:
                self._write_rein_log(f"VALIDATE FAILED | errors={len(result.errors)} | warnings={len(result.warnings)}")
                print(f"\n[ERROR] Workflow validation failed!")
                print(result.format_report())
                print()
                sys.exit(1)

            # Print warnings if any
            if result.warnings:
                print(f"[WARNING] {len(result.warnings)} validation warnings:")
                for warning in result.warnings:
                    print(f"  - {warning.field}: {warning.message}")
                print()

        except Exception as e:
            self._write_rein_log(f"VALIDATE ERROR | {str(e)}")
            # Don't fail on validation errors, just log them
            print(f"[WARNING] Validation engine error (continuing anyway): {e}\n")

    def _load_env_file(self, workflow_dir: str):
        """Load .env file from flow directory (delegates to ConfigLoader)"""
        self.config_loader.load_env_file(workflow_dir)

    def load_team(self, team_name: str) -> str:
        """Load team configuration and return tone (delegates to ConfigLoader)"""
        return self.config_loader.load_team(team_name)

    def load_specialist(self, specialist_name: str) -> str:
        """Load specialist instructions from MD file (delegates to ConfigLoader)"""
        return self.config_loader.load_specialist(specialist_name)

    def assemble_prompt(self, block: dict, team_tone: str) -> str:
        """Assemble full prompt from specialists + team tone + block prompt (PHASE 2.5)"""
        try:
            # Load specialist instructions
            specialist_text = ""

            # Support both old 'agents' (list) and new 'specialist' (single) format
            agents = block.get('agents', [])
            if block.get('specialist'):
                agents = [block.get('specialist')]

            for agent in agents:
                spec = self.load_specialist(agent)
                specialist_text += f"\n---\n{spec}"

            # Get block prompt
            prompt = block.get('prompt', '')

            # REFACTOR: Substitute task.input.* placeholders first
            import re
            if self.task_input:
                # Find {{ task.input.fieldname }} placeholders
                task_input_pattern = r'\{\{\s*task\.input\.(\w+)\s*\}\}'
                for match in re.finditer(task_input_pattern, prompt):
                    full_placeholder = match.group(0)
                    field_name = match.group(1)
                    if field_name in self.task_input:
                        value = self.task_input[field_name]
                        # If value is dict/list, convert to JSON string
                        if isinstance(value, (dict, list)):
                            value = json.dumps(value, ensure_ascii=False)
                        prompt = prompt.replace(full_placeholder, str(value))
                        self._write_rein_log(f"TASK INPUT SUBSTITUTED | {field_name} | value_len={len(str(value))}")

            # Substitute input files ({{ file.json }})
            # Parse prompt to find all {{ file.json }} placeholders (including spaces)
            # Find placeholders WITH spaces preserved
            placeholder_matches = re.finditer(r'\{\{([^}]+)\}\}', prompt)

            for match in placeholder_matches:
                full_placeholder = match.group(0)  # e.g., "{{ filename.json }}"
                filename = match.group(1).strip()  # e.g., "filename.json"

                # REFACTOR: Try task outputs first, then workflow directory
                file_path = None
                if self.task_dir:
                    task_output_path = os.path.join(self.task_dir, "outputs", filename)
                    if os.path.exists(task_output_path):
                        file_path = task_output_path

                # Fallback to workflow directory
                if not file_path:
                    workflow_path = os.path.join(self.workflow_dir, filename)
                    if os.path.exists(workflow_path):
                        file_path = workflow_path

                if file_path:
                    try:
                        with open(file_path) as f:
                            data = json.load(f)
                            # Extract just the data content if it's wrapped in envelope
                            if isinstance(data, dict) and 'result' in data:
                                result_str = data.get('result', '')
                                try:
                                    inner_data = json.loads(result_str)
                                    data = inner_data
                                except (json.JSONDecodeError, ValueError, TypeError):
                                    pass
                            # Use the FULL placeholder text (with spaces preserved)
                            prompt = prompt.replace(full_placeholder, json.dumps(data, ensure_ascii=False))
                            self._write_rein_log(f"FILE SUBSTITUTED | {filename} | from={file_path} | size={len(json.dumps(data))}")
                    except Exception as e:
                        self._write_rein_log(f"FILE SUBSTITUTE ERROR | {file_path} | {str(e)}")
                else:
                    self._write_rein_log(f"FILE NOT FOUND | {filename} (checked task outputs and workflow dir)")

            # Build final prompt
            full_prompt = f"""{team_tone}

{specialist_text}

---

{prompt}"""
            # Debug logging
            self._write_rein_log(f"ASSEMBLED PROMPT | len={len(full_prompt)} | first_200={full_prompt[:200]}")
            return full_prompt
        except Exception as e:
            self._write_rein_log(f"PROMPT ASSEMBLY ERROR | {str(e)}")
            return ""

    def call_claude(self, prompt: str, stage: str) -> str:
        """Call Claude API (delegates to ClaudeClient)"""
        return self.claude_client.call(prompt, stage)

    def _prepare_input_dir(self, block_name: str, depends_on: list) -> str:
        """Create task/block/inputs/ directory (v3.0: no symlinks, direct reads via task_dir)"""
        # Get block directory (creates inputs/, outputs/, logs/)
        block_dir = self._get_block_dir(block_name)
        input_dir = os.path.join(block_dir, "inputs")

        # Log dependencies for debugging (scripts read directly from task_dir/dep/outputs/)
        for dep in depends_on:
            dep_output = os.path.join(self.task_dir, dep, "outputs", "result.json")
            if os.path.exists(dep_output):
                self._write_rein_log(f"INPUT DEP | {block_name} <- {dep}/outputs/result.json")
            else:
                self._write_rein_log(f"INPUT WARN | {block_name} | dependency not ready: {dep}")

        return input_dir

    def _run_logic(self, script_path: str, data_file: str, workflow_dir: str,
                   input_dir: str = None, block_config: dict = None) -> bool:
        """Run logic script (delegates to LogicRunner)"""
        block_name = block_config.get('name') if block_config else None
        block_dir = self._get_block_dir(block_name) if block_name and self.task_dir else None
        depends_on = block_config.get('depends_on', []) if block_config else []

        # Create LogicRunner with current context
        runner = LogicRunner(
            task_dir=self.task_dir,
            workflow_dir=workflow_dir,
            task_id=self.task_id,
            task_input=self.task_input,
            logger=self._write_rein_log
        )

        return runner.run(
            script_path=script_path,
            output_file=data_file,
            block_name=block_name,
            block_dir=block_dir,
            input_dir=input_dir,
            depends_on=depends_on,
            block_config=block_config
        )

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
            self._write_rein_log(f"STATE LOADED | {completed_count}/{len(self.processes)} processes restored from DB")
        except Exception as e:
            self._write_rein_log(f"STATE LOAD ERROR | {str(e)}")

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
            # Support both 'name' (old) and 'stage' (new Phase 2.5)
            name = block.get('name') or block.get('stage', 'unknown')
            depends_on = block.get('depends_on', [])
            phase = self._calculate_phase(depends_on, block_phases)
            block_phases[name] = phase

        # Second pass - create processes with phases
        for block in self.all_blocks:
            # Support both 'name' (old) and 'stage' (new Phase 2.5)
            name = block.get('name') or block.get('stage', 'unknown')
            command = block.get('command', '')  # Make optional for Phase 2.5 blocks
            depends_on = block.get('depends_on', [])
            phase = block_phases[name]
            blocking_pause = block.get('blocking_pause', True)  # default: True (safer)
            agent = block.get('agent', '')  # Get agent name from config
            uid = str(uuid.uuid4())[:8]  # Short UUID (8 chars)

            # STATE MACHINE: read next and max_runs from config (Phase 2.5.4)
            next_spec = block.get('next')
            max_runs = block.get('max_runs', 1)

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
                agent=agent,  # Add agent
                next_spec=next_spec,  # STATE MACHINE
                max_runs=max_runs  # STATE MACHINE
            )

            with self.lock:
                self.processes[uid] = process  # Use UID as key
                # Store block config for re-running (STATE MACHINE)
                self.block_configs[name] = block
            self.state.save_process(process)

    def _find_process_by_name(self, name: str) -> Optional[tuple]:
        """Find process by name, return (uid, process)"""
        with self.lock:
            for uid, proc in self.processes.items():
                if proc.name == name:
                    return (uid, proc)
        return None

    def _get_previous_blocks_status(self, block: dict) -> List[str]:
        """Get status of previous blocks - return list of failed block names"""
        failed_blocks = []
        with self.lock:
            for uid, proc in self.processes.items():
                if proc.status == "failed":
                    failed_blocks.append(proc.name)
        return failed_blocks

    def _should_execute_block(self, block: dict, previous_failed: List[str]) -> bool:
        """Check if block should be executed based on skip_if_previous_failed flag"""
        skip_if_failed = block.get('skip_if_previous_failed', False)

        if previous_failed and not skip_if_failed:
            # There were failures and this block doesn't skip-on-failure
            return False

        return True

    def _should_continue_after_failure(self, block: dict, block_failed: bool) -> bool:
        """Check if workflow should continue after block failure"""
        if not block_failed:
            return True  # No failure, continue

        continue_if_failed = block.get('continue_if_failed', True)
        return continue_if_failed

    def _evaluate_next_block(self, block: dict, result_data: dict) -> Optional[str]:
        """Evaluate next block specification and return next block name (STATE MACHINE Phase 2.5.4)

        Supports:
        - Simple string: next: "publish" -> always go to publish
        - Conditional list:
            next:
              - if: "{{ result.approved }}"
                goto: publish
              - else:
                goto: revision

        Args:
            block: Block configuration dict
            result_data: Result from block execution (parsed JSON or raw)

        Returns:
            Name of next block to trigger, or None if no next specified
        """
        next_spec = block.get('next')
        if not next_spec:
            return None

        name = block.get('name') or block.get('stage', 'unknown')

        # Simple string case
        if isinstance(next_spec, str):
            self._write_rein_log(f"NEXT SIMPLE | {name} -> {next_spec}")
            return next_spec

        # Conditional list case
        if isinstance(next_spec, list):
            for condition in next_spec:
                if 'else' in condition:
                    # Default/else branch - always matches if reached
                    goto = condition.get('goto') or condition.get('else')
                    self._write_rein_log(f"NEXT ELSE | {name} -> {goto}")
                    return goto

                if 'if' in condition:
                    condition_expr = condition['if']
                    goto = condition.get('goto')

                    # Evaluate condition - supports {{ result.field }} syntax
                    if self._evaluate_condition(condition_expr, result_data):
                        self._write_rein_log(f"NEXT IF | {name} | condition={condition_expr} -> {goto}")
                        return goto

        return None

    def _evaluate_condition(self, expr: str, result_data: dict) -> bool:
        """Evaluate a condition expression against result data

        Supports:
        - {{ result.approved }} - checks if result.approved is truthy
        - {{ result.status == 'approved' }} - equality check
        - {{ result.score > 0.8 }} - comparison
        """
        try:
            # Extract expression from {{ }}
            match = re.match(r'\{\{\s*(.+?)\s*\}\}', expr.strip())
            if not match:
                self._write_rein_log(f"CONDITION PARSE ERROR | no match: {expr}")
                return False

            inner_expr = match.group(1).strip()

            # Handle comparison operators
            for op in ['==', '!=', '>=', '<=', '>', '<']:
                if op in inner_expr:
                    parts = inner_expr.split(op, 1)
                    if len(parts) == 2:
                        left = self._resolve_path(parts[0].strip(), result_data)
                        right_str = parts[1].strip().strip("'\"")

                        # Try to convert right side to same type as left
                        if isinstance(left, bool):
                            right = right_str.lower() in ('true', '1', 'yes')
                        elif isinstance(left, (int, float)):
                            try:
                                right = float(right_str)
                            except (ValueError, TypeError):
                                right = right_str
                        else:
                            right = right_str

                        if op == '==':
                            return left == right
                        elif op == '!=':
                            return left != right
                        elif op == '>':
                            return left > right
                        elif op == '<':
                            return left < right
                        elif op == '>=':
                            return left >= right
                        elif op == '<=':
                            return left <= right

            # Simple truthy check: {{ result.approved }}
            value = self._resolve_path(inner_expr, result_data)
            return bool(value)

        except Exception as e:
            self._write_rein_log(f"CONDITION EVAL ERROR | {expr} | {str(e)}")
            return False

    def _resolve_path(self, path: str, data: dict) -> any:
        """Resolve a dot-separated path like 'result.approved' in data dict"""
        parts = path.split('.')
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return current

    def spawn_process(self, block: dict, team_tone: str = "") -> Optional[Process]:
        """Spawn a new block execution (PHASE 2.5: Claude API instead of subprocess)"""
        name = block.get('name') or block.get('stage', 'unknown')
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

        # Check if block should be skipped due to previous failures (FLOW CONTROL)
        previous_failed = self._get_previous_blocks_status(block)
        if not self._should_execute_block(block, previous_failed):
            self._write_rein_log(f"BLOCK SKIPPED | {name} | skip_if_previous_failed=false and failures detected")
            return "skipped"  # Return special marker for skipped blocks

        self.semaphore.acquire()

        try:
            # Find process
            result = self._find_process_by_name(name)
            if not result:
                raise Exception(f"Block {name} not found")

            uid, process = result
            process.status = "running"
            process.start_time = time.time()
            process.progress = 0
            process.pid = os.getpid()  # Use current process PID (no subprocess)

            self.state.save_process(process)

            # Log block start
            depends_str = f" | depends_on={process.depends_on}" if process.depends_on else ""
            agent_str = f" | agent={process.agent}" if process.agent else ""
            self._write_rein_log(f"BLOCK STARTED | {name}[{uid}] | phase={process.phase}{agent_str}{depends_str}")

            # Execute in background thread
            threading.Thread(
                target=self._execute_block,
                args=(uid, process, block, team_tone),
                daemon=True
            ).start()

            return process
        except Exception as e:
            self._write_rein_log(f"SPAWN ERROR | {name} | {str(e)}")
            self.semaphore.release()
            return None

    def _execute_block(self, uid: str, process: Process, block: dict, team_tone: str):
        """Execute block (PHASE 2.5: Call Claude API with Logic Phases)"""
        name = process.name
        block_failed = False
        try:
            process.progress = 25
            self.state.save_process(process)

            # Get workflow directory for relative logic paths
            workflow_dir = self.workflow_dir

            # Get logic configuration
            logic_config = block.get('logic', {})

            # Save file path (v3.0: task/block/outputs/result.json)
            output_dir = self._get_output_dir(name)
            save_file = os.path.join(output_dir, "result.json")
            os.makedirs(output_dir, exist_ok=True)

            # v2.5.5: Prepare input directory with symlinks to dependency outputs
            depends_on = block.get('depends_on', [])
            input_dir = self._prepare_input_dir(name, depends_on)

            # PRE-PHASE: Run pre-processing logic (before Claude)
            if logic_config.get('pre'):
                if not self._run_logic(logic_config['pre'], save_file, workflow_dir, input_dir, block):
                    raise Exception(f"Pre-phase logic failed: {logic_config['pre']}")

            # CLAUDE-PHASE: Call Claude API or run custom script
            custom_script = logic_config.get('custom')
            if custom_script:
                # CUSTOM MODE: Skip Claude call
                # If custom is a string (path) - run that script
                # If custom is True (boolean) - skip Claude, pre script already did everything
                if isinstance(custom_script, str):
                    self._write_rein_log(f"CUSTOM SCRIPT | {name} | script={custom_script}")
                    if not self._run_logic(custom_script, save_file, workflow_dir, input_dir, block):
                        raise Exception(f"Custom logic failed: {custom_script}")
                else:
                    self._write_rein_log(f"CUSTOM SKIP | {name} | pre script handled Claude call")
                process.progress = 75
            else:
                # Check if this is a PHASE 2.5 block (has agents/specialist + prompt) or old block (has command)
                has_agents_or_specialist = 'agents' in block or 'specialist' in block
                has_prompt = 'prompt' in block
                self._write_rein_log(f"DEBUG | block={name} | has_agents={has_agents_or_specialist} | has_prompt={has_prompt} | team_tone={bool(team_tone)}")
                if has_agents_or_specialist and has_prompt and team_tone:
                    # PHASE 2.5: Claude API execution
                    prompt = self.assemble_prompt(block, team_tone)
                    process.progress = 50
                    self.state.save_process(process)

                    # Call Claude
                    result = self.call_claude(prompt, name)
                    process.progress = 75
                else:
                    # FALLBACK: Old system (shell execution)
                    command = block.get('command', '')
                    if not command:
                        raise Exception(f"No command or agents+prompt for block {name}")

                    env = os.environ.copy()
                    env['REIN_LOG_DIR'] = self.log_dir

                    proc = subprocess.Popen(
                        command, shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=env
                    )

                    stdout, stderr = proc.communicate()
                    result = stdout.decode() if stdout else ""

                    if proc.returncode != 0:
                        self._write_rein_log(f"COMMAND ERROR | {name} | {stderr.decode() if stderr else ''}")

                    process.progress = 75

                # Save result from Claude (only if not custom - custom script saves its own result)
                with open(save_file, 'w') as f:
                    json.dump({
                        "stage": name,
                        "result": result,
                        "timestamp": datetime.now().isoformat()
                    }, f, indent=2, ensure_ascii=False)

            # POST-PHASE: Run post-processing logic (after Claude)
            if logic_config.get('post'):
                if not self._run_logic(logic_config['post'], save_file, workflow_dir, input_dir, block):
                    raise Exception(f"Post-phase logic failed: {logic_config['post']}")

            # VALIDATE-PHASE: Run validation logic
            if logic_config.get('validate'):
                if not self._run_logic(logic_config['validate'], save_file, workflow_dir, input_dir, block):
                    raise Exception(f"Validate-phase logic failed: {logic_config['validate']}")

            process.progress = 100
            process.status = "done"
            process.exit_code = 0
            self.state.save_process(process)

            # Generate readable MD after block completes (works for both custom and regular blocks)
            if self.config.get('readable_outputs', False) and os.path.exists(save_file):
                try:
                    with open(save_file) as f:
                        data = json.load(f)
                    result_content = data.get('result', '')
                    self._save_readable_output(save_file, name, result_content)
                except Exception as e:
                    self._write_rein_log(f"READABLE OUTPUT ERROR | {name} | {str(e)}")

            self._write_rein_log(f"BLOCK COMPLETED | {name}[{uid}] | saved={save_file}")
            self.completed.add(name)

            # STATE MACHINE: Evaluate and trigger next block (Phase 2.5.4)
            if block.get('next'):
                try:
                    # Parse result data for condition evaluation
                    result_data = {}
                    if os.path.exists(save_file):
                        with open(save_file) as f:
                            saved_data = json.load(f)
                            # Get inner result (may be dict or string)
                            inner_result = saved_data.get('result', {})
                            if isinstance(inner_result, dict):
                                parsed_result = inner_result
                            elif isinstance(inner_result, str):
                                # Try to parse as JSON
                                try:
                                    parsed_result = json.loads(inner_result)
                                except (json.JSONDecodeError, ValueError):
                                    parsed_result = {'raw': inner_result}
                            else:
                                parsed_result = {'value': inner_result}
                            # Wrap in 'result' for {{ result.field }} conditions
                            result_data = {'result': parsed_result, '_stage': name, '_saved': saved_data}

                    next_block_name = self._evaluate_next_block(block, result_data)

                    if next_block_name:
                        # Check max_runs for loop protection
                        current_runs = self.run_counts.get(next_block_name, 0)
                        next_block_config = self.block_configs.get(next_block_name)
                        max_runs = next_block_config.get('max_runs', 1) if next_block_config else 1

                        if current_runs >= max_runs:
                            self._write_rein_log(f"NEXT BLOCKED | {next_block_name} | run_count={current_runs} >= max_runs={max_runs}")
                        else:
                            # Increment run count and add to next queue
                            self.run_counts[next_block_name] = current_runs + 1

                            with self.lock:
                                # Remove from completed to allow re-run
                                self.completed.discard(next_block_name)
                                # Reset process status to waiting
                                for proc_uid, proc in self.processes.items():
                                    if proc.name == next_block_name:
                                        proc.status = "waiting"
                                        proc.progress = 0
                                        proc.run_count = self.run_counts[next_block_name]
                                        self.state.save_process(proc)
                                        break
                                # Add to next queue
                                self.next_queue.append((next_block_name, result_data))

                            self._write_rein_log(f"NEXT QUEUED | {name} -> {next_block_name} | run={self.run_counts[next_block_name]}/{max_runs}")
                except Exception as e:
                    self._write_rein_log(f"NEXT EVAL ERROR | {name} | {str(e)}")

        except Exception as e:
            self._write_rein_log(f"BLOCK FAILED | {name}[{uid}] | {str(e)}")
            process.status = "failed"
            process.exit_code = 1
            block_failed = True
            self.state.save_process(process)
            self.completed.add(name)

            # Check continue_if_failed flag (FLOW CONTROL)
            if not self._should_continue_after_failure(block, block_failed):
                self._write_rein_log(f"WORKFLOW STOPPED | {name} | continue_if_failed=false")
                with self.lock:
                    self.stop_workflow = True
                    self.stop_reason = f"Critical failure in block '{name}' (continue_if_failed=false)"
        finally:
            self.semaphore.release()

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
                            except (json.JSONDecodeError, ValueError, KeyError):
                                pass
                except Exception:
                    pass

            output_thread = threading.Thread(target=read_output, daemon=True)
            output_thread.start()

            # Also read stderr to prevent pipe buffer overflow
            def read_errors():
                try:
                    if proc.stderr:
                        for line in proc.stderr:
                            pass  # Discard stderr
                except Exception:
                    pass

            error_thread = threading.Thread(target=read_errors, daemon=True)
            error_thread.start()

            # Wait for process to complete
            while self.running and proc.poll() is None:
                try:
                    process.cpu_percent = ps_proc.cpu_percent(interval=0.1)
                    process.memory_mb = ps_proc.memory_info().rss / 1024 / 1024
                except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
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
            self._write_rein_log(f"PROCESS {'COMPLETED' if process.status == 'done' else 'FAILED'} | {name}[{uid}] | pid={process.pid} | exit_code={exit_code} | elapsed={elapsed:.1f}s | verification={verification_msg}")

        except Exception as e:
            # On error, still mark as failed and save
            process.status = "failed"
            with self.lock:
                self.completed.add(name)
            self.state.save_process(process)
            self._write_rein_log(f"PROCESS ERROR | {name}[{uid}] | exception={str(e)}")
        finally:
            self.semaphore.release()

    def run_workflow(self):
        """Execute workflow with dependency management"""
        # Support both 'name' (old) and 'stage' (new Phase 2.5)
        pending = {(block.get('name') or block.get('stage', 'unknown')): block for block in self.all_blocks}
        spawned = set()
        skipped = set()
        loop_count = 0
        start_time = time.time() if self.timeout else None

        # Load team tone for PHASE 2.5
        team_tone = ""
        if self.team_name:
            team_tone = self.load_team(self.team_name)

        while pending or self.processes or self.next_queue:
            loop_count += 1

            # Check if workflow should stop due to critical failure (FLOW CONTROL)
            if self.stop_workflow:
                self._write_rein_log(f"WORKFLOW STOPPING | reason={self.stop_reason}")
                self._kill_remaining_processes(self.stop_reason or "workflow stop requested")
                break

            # Check if timeout exceeded
            if self.timeout and start_time:
                elapsed = time.time() - start_time
                if elapsed > self.timeout:
                    self._write_rein_log(f"TIMEOUT EXCEEDED | elapsed={elapsed:.1f}s > limit={self.timeout}s")
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
                    self._write_rein_log(f"WORKFLOW PAUSED | skipping spawn of {name}")
                    continue

                # Check timeout approaching
                if self.timeout and start_time:
                    elapsed = time.time() - start_time
                    if elapsed > self.timeout * 0.95:  # Don't spawn if 95% timeout used
                        self._write_rein_log(f"TIMEOUT APPROACHING | stopping new spawns at {elapsed:.1f}s")
                        break

                result = self.spawn_process(pending[name], team_tone)
                if result == "skipped":
                    # Block was skipped due to previous failures
                    skipped.add(name)
                    del pending[name]
                    # Mark as "skipped" in completed to allow dependent blocks to proceed
                    self.completed.add(name)
                elif result:
                    spawned.add(name)
                    del pending[name]
                else:
                    # Failed to spawn, might be semaphore issue or dependencies
                    pass

            # STATE MACHINE: Process next_queue for triggered blocks (Phase 2.5.4)
            while self.next_queue and not self.workflow_paused:
                with self.lock:
                    if not self.next_queue:
                        break
                    next_block_name, trigger_data = self.next_queue.pop(0)

                # Get block config
                block_config = self.block_configs.get(next_block_name)
                if not block_config:
                    self._write_rein_log(f"NEXT ERROR | block not found: {next_block_name}")
                    continue

                # Check timeout before spawning
                if self.timeout and start_time:
                    elapsed = time.time() - start_time
                    if elapsed > self.timeout * 0.95:
                        self._write_rein_log(f"NEXT TIMEOUT | stopping new spawns at {elapsed:.1f}s")
                        break

                # Spawn the next block
                self._write_rein_log(f"NEXT SPAWN | {next_block_name} | triggered by state machine")
                result = self.spawn_process(block_config, team_tone)
                if result and result != "skipped":
                    # Block was spawned successfully
                    pass
                elif result == "skipped":
                    self._write_rein_log(f"NEXT SKIPPED | {next_block_name}")
                else:
                    # Failed to spawn - put back in queue for retry
                    with self.lock:
                        self.next_queue.insert(0, (next_block_name, trigger_data))
                    break  # Exit next_queue loop to wait for semaphore

            # Wait a bit for processes to complete
            time.sleep(0.5)

            # Check if all done (all pending spawned, all processes completed, and next_queue empty)
            if not pending and self.all_completed() and not self.next_queue:
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
            self._write_rein_log(f"REIN FINISHED | completed={completed} | failed={failed} | total={len(self.processes)}")

            # v3.0: Update task status file and task.json
            if self.task_dir:
                status = "completed" if failed == 0 else "failed"
                # Update status file (v3.0: state/status)
                with open(os.path.join(self.task_dir, "state", "status"), "w") as f:
                    f.write(f"{status}\n")
                # Update task.json (v3.0: input/task.json)
                task_json_path = os.path.join(self.task_dir, "input", "task.json")
                if os.path.exists(task_json_path):
                    with open(task_json_path) as f:
                        task_data = json.load(f)
                    task_data["status"] = status
                    task_data["completed"] = datetime.now().isoformat()
                    task_data["blocks_completed"] = completed
                    task_data["blocks_failed"] = failed
                    task_data["blocks_total"] = len(self.processes)
                    with open(task_json_path, "w") as f:
                        json.dump(task_data, f, indent=2, ensure_ascii=False)
                self._write_rein_log(f"TASK STATUS | {self.task_id} | status={status}")

            # Handle task output (copy results to task output_dir)
            output_dir = self.all_blocks[0].get('output_dir') if hasattr(self, 'all_blocks') and self.all_blocks else None
            if not output_dir:
                # Try to get from config
                output_dir = self.config.get('output_dir') if hasattr(self, 'config') else None

            if output_dir:
                try:
                    os.makedirs(output_dir, exist_ok=True)
                    # Copy workflow files (YAML, .env, logs) from workflow directory
                    workflow_dir = os.path.dirname(self.workflow_file) if hasattr(self, 'workflow_file') else None
                    if workflow_dir:
                        for f in os.listdir(workflow_dir):
                            if f.endswith(('.json', '.yaml', '.env')):
                                src = os.path.join(workflow_dir, f)
                                dst = os.path.join(output_dir, f)
                                if os.path.isfile(src):
                                    import shutil
                                    try:
                                        shutil.copy2(src, dst)
                                    except (OSError, IOError, shutil.Error):
                                        pass
                    self._write_rein_log(f"OUTPUT SAVED | {output_dir}")
                except Exception as e:
                    self._write_rein_log(f"OUTPUT SAVE ERROR | {str(e)}")

            # Update task status if task_dir is set
            if hasattr(self, 'config') and 'status_path' in self.config:
                status = 'completed' if failed == 0 else 'failed'
                _update_task_status(
                    self.config['status_path'],
                    status,
                    progress=100,
                    blocks_completed=completed,
                    blocks_total=len(self.processes)
                )

                # Handle callback to memory (if configured)
                if hasattr(self, 'config') and 'task_config' in self.config:
                    task_config = self.config['task_config']
                    if task_config.get('callback', {}).get('save_to_memory'):
                        _save_task_to_memory(
                            output_dir,
                            task_config.get('callback', {}).get('memory_config', {})
                        )

            print(f"\n[OK] Run completed. Logs saved to: {self.run_dir}")
            if output_dir:
                print(f"[OK] Results saved to: {output_dir}")
        except Exception as e:
            print(f"[ERROR] Error saving run summary: {e}")
            self._write_rein_log(f"FINALIZE ERROR | {str(e)}")

    def _kill_remaining_processes(self, reason: str = "timeout"):
        """Kill remaining running processes gracefully"""
        with self.lock:
            for name, process in self.processes.items():
                if process.status == "running" and process.pid:
                    try:
                        os.kill(process.pid, signal.SIGTERM)
                        self._write_rein_log(f"SIGTERM SENT | {name} | pid={process.pid} | reason={reason}")
                    except Exception as e:
                        self._write_rein_log(f"KILL FAILED | {name} | {str(e)}")

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
        self._write_rein_log(f"PAUSE_SINGLE | {process.name}[{process_id}] | previous_status={process._previous_status}")
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
        self._write_rein_log(f"RESUME_SINGLE | {process.name}[{process_id}] | resumed_to={process.status}")
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
                    self._write_rein_log(f"KILL SENT | {process.name}[{process_id}] | pid={process.pid}")
                except Exception as e:
                    self._write_rein_log(f"KILL FAILED | {process.name}[{process_id}] | {str(e)}")

            # Mark as cancelled (won't restart on resume)
            process.status = "cancelled"
            self.state.save_process(process)
            self._write_rein_log(f"CANCEL_SINGLE | {process.name}[{process_id}] | previous_status={process.status}")

        return True

    def pause_workflow(self) -> bool:
        """Pause entire workflow - stops spawning new processes"""
        with self.lock:
            if self.workflow_paused:
                return False  # Already paused

            self.workflow_paused = True
            self.workflow_paused_at = time.time()

        self._write_rein_log(f"PAUSE_WORKFLOW | Workflow paused, no new processes will spawn")
        return True

    def resume_workflow(self) -> bool:
        """Resume paused workflow - allows spawning to continue"""
        with self.lock:
            if not self.workflow_paused:
                return False  # Not paused

            self.workflow_paused = False
            self.workflow_paused_at = None

        self._write_rein_log(f"RESUME_WORKFLOW | Workflow resumed, spawning will continue")
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
                self._write_rein_log(f"COMMAND | pause {name} | SUCCESS")
            else:
                self._write_rein_log(f"COMMAND | pause {name} | FAILED")

        elif action == "resume" and len(parts) > 1:
            name = parts[1]
            if self.resume_single(name):
                self._write_rein_log(f"COMMAND | resume {name} | SUCCESS")
            else:
                self._write_rein_log(f"COMMAND | resume {name} | FAILED")

        elif action == "pause-workflow":
            if self.pause_workflow():
                self._write_rein_log(f"COMMAND | pause-workflow | SUCCESS")
            else:
                self._write_rein_log(f"COMMAND | pause-workflow | FAILED (already paused)")

        elif action == "resume-workflow":
            if self.resume_workflow():
                self._write_rein_log(f"COMMAND | resume-workflow | SUCCESS")
            else:
                self._write_rein_log(f"COMMAND | resume-workflow | FAILED (not paused)")

        elif action == "status":
            with self.lock:
                running = sum(1 for p in self.processes.values() if p.status == "running")
                paused = sum(1 for p in self.processes.values() if p.status == "paused")
                done = sum(1 for p in self.processes.values() if p.status == "done")
                failed = sum(1 for p in self.processes.values() if p.status == "failed")
                waiting = sum(1 for p in self.processes.values() if p.status == "waiting")
                workflow_paused = "yes" if self.workflow_paused else "no"
            msg = f"COMMAND | status | running={running} paused={paused} done={done} failed={failed} waiting={waiting} workflow_paused={workflow_paused}"
            self._write_rein_log(msg)

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
                    self._write_rein_log(msg)

        elif action == "list":
            # List all processes with their UIDs
            with self.lock:
                for uid, proc in self.processes.items():
                    self._write_rein_log(f"PROCESS | {proc.name}[{uid}] | status={proc.status} pid={proc.pid}")

        elif action == "cancel" and len(parts) > 1:
            identifier = parts[1]
            if self.cancel_single(identifier):
                self._write_rein_log(f"COMMAND | cancel {identifier} | SUCCESS")
            else:
                self._write_rein_log(f"COMMAND | cancel {identifier} | FAILED")

        else:
            self._write_rein_log(f"COMMAND | unknown | {cmd}")

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
                self._write_rein_log(f"STDIN ERROR | {str(e)}")

        thread = threading.Thread(target=read_stdin, daemon=True)
        thread.start()

    def start_socket_server(self, socket_path: Optional[str] = None):
        """Start Unix domain socket server for async command handling"""
        # Use GUID-based socket path if GUID is set
        if socket_path is None:
            if self.guid:
                socket_path = f"/tmp/rein-{self.guid}.sock"
            else:
                socket_path = "/tmp/rein.sock"

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

                self._write_rein_log(f"SOCKET SERVER | listening on {socket_path}")

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
                                    self._write_rein_log(f"SOCKET ACCEPT ERROR | {str(e)}")
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
                                    except OSError:
                                        pass
                finally:
                    # Cleanup on shutdown
                    for client in clients:
                        try:
                            client.close()
                        except OSError:
                            pass
                    sock.close()
                    try:
                        os.unlink(socket_path)
                    except OSError:
                        pass
                    self._write_rein_log(f"SOCKET SERVER | stopped")

            except Exception as e:
                self._write_rein_log(f"SOCKET SERVER ERROR | {str(e)}")

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


def _update_task_status(status_path, status, **kwargs):
    """Update task status.json file"""
    try:
        if os.path.exists(status_path):
            with open(status_path) as f:
                data = json.load(f)
        else:
            data = {'created_at': datetime.now().isoformat()}

        data['status'] = status
        data.update(kwargs)

        if status == 'running':
            if 'started_at' not in data or not data['started_at']:
                data['started_at'] = datetime.now().isoformat()
        elif status in ['completed', 'failed']:
            if 'completed_at' not in data or not data['completed_at']:
                data['completed_at'] = datetime.now().isoformat()

        os.makedirs(os.path.dirname(status_path), exist_ok=True)
        with open(status_path, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[WARN] Failed to update status: {e}")

def _save_task_to_memory(output_dir, memory_config):
    """Save task results to memory system (optional callback)"""
    try:
        if not output_dir or not memory_config:
            return

        # Collect all JSON files from output_dir
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

        # Try to save to memory via mem-cli if available
        mem_cli = '/server/hq/tools/mem-cli.sh'
        if os.path.exists(mem_cli):
            try:
                # Build content summary
                content = f"Task completed with results:\n"
                for fname in sorted(result_files.keys()):
                    content += f"- {fname}\n"

                # Build tags
                tags = memory_config.get('tags', [])
                tags_str = ','.join(tags) if tags else 'type:artifact,stage:completed'

                # Try mem register if guid provided
                guid = memory_config.get('guid')
                if guid:
                    import subprocess
                    cmd = [mem_cli, 'register', guid, content, tags_str]
                    subprocess.run(cmd, capture_output=True, timeout=10)
                    print(f"[MEMORY] Task results saved to memory")
            except Exception as e:
                print(f"[WARN] Memory callback failed: {e}")
    except Exception as e:
        print(f"[WARN] Error in _save_task_to_memory: {e}")

def load_config(config_path: str) -> dict:
    """Load YAML config"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def run_daemon(agents_dir: str, interval: int = 5, no_ui: bool = True):
    """
    Run Rein as daemon, watching for pending tasks.

    Monitors {agents_dir}/tasks/ for tasks with status.json containing status="pending".
    When found, executes the task and updates status to running/completed/failed.
    """
    from datetime import datetime

    tasks_dir = os.path.join(agents_dir, "tasks")

    print(f"[REIN DAEMON] Started", flush=True)
    print(f"[REIN DAEMON] Watching: {tasks_dir}", flush=True)
    print(f"[REIN DAEMON] Interval: {interval}s", flush=True)
    print(f"[REIN DAEMON] Press Ctrl+C to stop", flush=True)
    print(flush=True)

    while True:
        try:
            # Find pending tasks
            if os.path.exists(tasks_dir):
                for task_name in os.listdir(tasks_dir):
                    task_path = os.path.join(tasks_dir, task_name)
                    if not os.path.isdir(task_path):
                        continue

                    status_file = os.path.join(task_path, "state", "status.json")
                    if not os.path.exists(status_file):
                        continue

                    try:
                        with open(status_file) as f:
                            status_data = json.load(f)
                    except:
                        continue

                    if status_data.get("status") != "pending":
                        continue

                    # Found pending task!
                    print(f"[DAEMON] Found pending task: {task_name}", flush=True)

                    flow_name = status_data.get("flow", "")
                    question = status_data.get("question", "")

                    if not flow_name:
                        print(f"[DAEMON] ERROR: No flow specified for {task_name}")
                        status_data["status"] = "failed"
                        status_data["error"] = "No flow specified"
                        with open(status_file, "w") as f:
                            json.dump(status_data, f, indent=2)
                        continue

                    # Update status to running
                    status_data["status"] = "running"
                    status_data["started_at"] = datetime.now().isoformat()
                    with open(status_file, "w") as f:
                        json.dump(status_data, f, indent=2)

                    print(f"[DAEMON] Executing: flow={flow_name}", flush=True)
                    print(f"[DAEMON] Question: {question}", flush=True)
                    print(f"[DAEMON] Task path: {task_path}", flush=True)

                    # Find flow config
                    flow_path = os.path.join(agents_dir, "flows", flow_name, f"{flow_name}.yaml")
                    if not os.path.exists(flow_path):
                        print(f"[DAEMON] ERROR: Flow not found: {flow_path}")
                        status_data["status"] = "failed"
                        status_data["error"] = f"Flow not found: {flow_name}"
                        status_data["completed_at"] = datetime.now().isoformat()
                        with open(status_file, "w") as f:
                            json.dump(status_data, f, indent=2)
                        continue

                    # Execute task
                    log_file = os.path.join(task_path, "state", "rein.log")
                    exit_code_file = os.path.join(task_path, "state", "exit_code")

                    try:
                        # Run Rein for this task
                        config = load_config(flow_path)

                        # Setup task input - use question text directly
                        if question:
                            task_input = {"task": question}  # "task" key is what ProcessManager expects
                        else:
                            # Try to read from input/task.json or input/question.txt
                            task_json = os.path.join(task_path, "input", "task.json")
                            question_txt = os.path.join(task_path, "input", "question.txt")
                            if os.path.exists(task_json):
                                with open(task_json) as f:
                                    task_input = json.load(f)
                            elif os.path.exists(question_txt):
                                with open(question_txt) as f:
                                    task_input = {"task": f.read().strip()}
                            else:
                                task_input = {}

                        # Create ProcessManager like main() does
                        manager = ProcessManager(
                            max_parallel=config.get('semaphore', 3),
                            flow_name=flow_name,
                            task_input=task_input,
                            agents_dir=agents_dir
                        )

                        # Use existing task directory
                        manager.task_id = task_name
                        manager.task_dir = task_path
                        manager.run_dir = task_path
                        manager.log_dir = os.path.join(task_path, "state")
                        manager.rein_log_file = log_file
                        manager.db_path = os.path.join(task_path, "state", "rein.db")
                        os.makedirs(manager.log_dir, exist_ok=True)
                        manager.state = ReinState(manager.db_path, resume=False)

                        # Load workflow config
                        manager.load_config(config, workflow_file=flow_path)

                        # Redirect stdout to log file
                        with open(log_file, "w") as lf:
                            old_stdout = sys.stdout
                            sys.stdout = lf
                            try:
                                manager.run_workflow()
                                exit_code = 0
                            except Exception as e:
                                print(f"[ERROR] {e}")
                                import traceback
                                traceback.print_exc()
                                exit_code = 1
                            finally:
                                sys.stdout = old_stdout

                        # Write exit code
                        with open(exit_code_file, "w") as f:
                            f.write(str(exit_code))

                        # Update final status
                        status_data["status"] = "completed" if exit_code == 0 else "failed"
                        status_data["completed_at"] = datetime.now().isoformat()
                        if exit_code != 0:
                            status_data["error"] = f"Exit code: {exit_code}"

                        print(f"[DAEMON] Task {task_name}: {status_data['status']}", flush=True)

                    except Exception as e:
                        status_data["status"] = "failed"
                        status_data["error"] = str(e)
                        status_data["completed_at"] = datetime.now().isoformat()
                        print(f"[DAEMON] Task {task_name} FAILED: {e}")

                    with open(status_file, "w") as f:
                        json.dump(status_data, f, indent=2)

            time.sleep(interval)

        except KeyboardInterrupt:
            print("\n[DAEMON] Shutting down...")
            break
        except Exception as e:
            print(f"[DAEMON] Error in main loop: {e}")
            time.sleep(interval)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Rein - Workflow Orchestrator')
    parser.add_argument('config', nargs='?', help='Path to YAML configuration file (or use --flow/--task)')
    parser.add_argument('--flow', metavar='FLOW_NAME', help='Flow name (creates new task automatically)')
    parser.add_argument('--input', metavar='JSON', help='Input parameters as JSON (used with --flow)')
    parser.add_argument('--task-dir', metavar='DIR', help='Task directory with task.md (used with --flow)')
    parser.add_argument('--question', metavar='FILE', help='Question file path (simple question without task dir)')
    parser.add_argument('--task', metavar='TASK_DIR', help='Task directory (e.g., /path/to/tasks/task-001)')
    parser.add_argument('--status', metavar='TASK_ID', help='Show task status')
    parser.add_argument('--pause', action='store_true', help='Start workflow in paused state')
    parser.add_argument('--resume', metavar='RUN_ID', help='Resume from previous run (RUN_ID like 20251230-142345)')
    parser.add_argument('--no-ui', action='store_true', help='Run without Rich UI (for scripts/non-terminals)')
    parser.add_argument('--agents-dir', metavar='PATH', default='/server/agents',
                        help='Agents directory (specialists, teams, flows, tasks). Default: /server/agents')
    parser.add_argument('--daemon', action='store_true',
                        help='Run as daemon, watching for pending tasks')
    parser.add_argument('--daemon-interval', type=int, default=5,
                        help='Daemon check interval in seconds (default: 5)')

    args = parser.parse_args()

    # Handle --daemon mode
    if args.daemon:
        run_daemon(args.agents_dir, args.daemon_interval, args.no_ui)
        sys.exit(0)

    # Handle --status command
    if args.status:
        agents_dir = getattr(args, 'agents_dir', '/server/agents')
        tasks_root = os.path.join(agents_dir, "tasks")
        task_dir = os.path.join(tasks_root, args.status)
        # v3.0: paths changed to input/task.json and state/status
        task_json_path = os.path.join(task_dir, "input", "task.json")
        status_path = os.path.join(task_dir, "state", "status")

        if not os.path.exists(task_dir):
            print(f"[ERROR] Task not found: {args.status}")
            sys.exit(1)

        # Read task.json
        if os.path.exists(task_json_path):
            with open(task_json_path) as f:
                task_data = json.load(f)
            print(f"\n[TASK] ID: {task_data.get('id')}")
            print(f"[TASK] Flow: {task_data.get('flow')}")
            print(f"[TASK] Created: {task_data.get('created')}")
            print(f"[TASK] Status: {task_data.get('status')}")
            if task_data.get('input'):
                print(f"[TASK] Input: {json.dumps(task_data.get('input'), ensure_ascii=False)}")

        # Read status file
        if os.path.exists(status_path):
            with open(status_path) as f:
                print(f"[STATUS] {f.read().strip()}")

        # List outputs
        outputs_dir = os.path.join(task_dir, "outputs")
        if os.path.exists(outputs_dir):
            outputs = os.listdir(outputs_dir)
            if outputs:
                print(f"\n[OUTPUTS] {len(outputs)} files:")
                for f in sorted(outputs):
                    fpath = os.path.join(outputs_dir, f)
                    size = os.path.getsize(fpath)
                    print(f"  - {f} ({size} bytes)")
        print()
        sys.exit(0)

    # Handle --flow mode (REFACTOR: create task and run flow)
    flow_path = None
    task_id = None
    task_input = None

    if args.flow:
        flow_name = args.flow
        agents_dir = getattr(args, 'agents_dir', '/server/agents')
        flow_path = os.path.join(agents_dir, 'flows', flow_name, f'{flow_name}.yaml')

        if not os.path.exists(flow_path):
            print(f"[ERROR] Flow not found: {flow_path}")
            sys.exit(1)

        # Parse input: --question, --task-dir or --input
        question_file = getattr(args, 'question', None)
        task_dir_provided = getattr(args, 'task_dir', None)

        if question_file:
            # Simple question file - read and use as task
            if not os.path.exists(question_file):
                print(f"[ERROR] Question file not found: {question_file}")
                sys.exit(1)
            with open(question_file, 'r') as f:
                task_content = f.read()
            task_input = {"task": task_content}
            # Extract directories from question file location for context
            question_dir = os.path.dirname(os.path.abspath(question_file))
            context_dir = os.path.join(question_dir, 'context')
            if os.path.isdir(context_dir):
                # If context/ subdirectory exists, include it
                task_content += f"\n\nContext files available in: {context_dir}"
                task_input = {"task": task_content}
        elif task_dir_provided:
            # Read task.md from directory
            task_md_path = os.path.join(task_dir_provided, 'task.md')
            if not os.path.exists(task_md_path):
                print(f"[ERROR] task.md not found in: {task_dir_provided}")
                sys.exit(1)
            with open(task_md_path, 'r') as f:
                task_content = f.read()
            task_input = {"task": task_content}
        elif args.input:
            try:
                task_input = json.loads(args.input)
            except json.JSONDecodeError as e:
                print(f"[ERROR] Invalid JSON input: {e}")
                sys.exit(1)
        else:
            task_input = {}

        # Create task directory (will be done in ProcessManager)
        config = load_config(flow_path)

        # Create manager with task creation
        manager = ProcessManager(
            max_parallel=config.get('semaphore', 3),
            flow_name=flow_name,
            task_input=task_input,
            agents_dir=agents_dir
        )

        # Use provided task-dir or create new
        if task_dir_provided:
            task_dir_provided = task_dir_provided.rstrip('/')
            task_id = os.path.basename(task_dir_provided)
            manager.task_id = task_id
            manager.task_dir = task_dir_provided
            os.makedirs(os.path.join(task_dir_provided, "outputs"), exist_ok=True)
        else:
            task_id = manager.create_task(flow_name, task_input)
            manager.task_id = task_id
            manager.task_dir = os.path.join(manager.tasks_root, task_id)

        manager.run_dir = manager.task_dir
        manager.log_dir = os.path.join(manager.task_dir, "state")  # v3.0: state/ for logs
        manager.rein_log_file = os.path.join(manager.task_dir, "state", "rein.log")
        manager.db_path = os.path.join(manager.task_dir, "state", "rein.db")
        os.makedirs(manager.log_dir, exist_ok=True)
        manager.state = ReinState(manager.db_path, resume=False)

        # Load workflow config
        manager.load_config(config, workflow_file=flow_path)

        print(f"\n[TASK] ID: {task_id}")
        print(f"[TASK] Flow: {flow_name}")
        print(f"[TASK] Directory: {manager.task_dir}")
        if task_input and task_input.get('task'):
            # Truncate long task content for display
            task_preview = task_input['task'][:100] + "..." if len(task_input.get('task', '')) > 100 else task_input.get('task', '')
            print(f"[TASK] Input: {task_preview}")

    # Handle task mode (load flow from task.yaml)
    elif args.task:
        task_dir = args.task.rstrip('/')
        task_yaml_path = os.path.join(task_dir, 'task.yaml')
        status_path = os.path.join(task_dir, 'status.json')

        if not os.path.exists(task_yaml_path):
            print(f"[ERROR] Task file not found: {task_yaml_path}")
            sys.exit(1)

        # Load task configuration
        with open(task_yaml_path) as f:
            task_config = yaml.safe_load(f)

        # Get flow name from task
        flow_name = task_config.get('flow')
        if not flow_name:
            print("[ERROR] Task must specify 'flow' field")
            sys.exit(1)

        # Find flow in agents/flows/
        agents_dir = getattr(args, 'agents_dir', '/server/agents')
        flow_path = os.path.join(agents_dir, 'flows', flow_name, f'{flow_name}.yaml')
        if not os.path.exists(flow_path):
            print(f"[ERROR] Flow not found: {flow_path}")
            sys.exit(1)

        config = load_config(flow_path)

        # Update config with task-specific output path
        output_dir = task_config.get('output_dir', './outputs')
        output_dir = os.path.join(task_dir, output_dir.lstrip('./'))
        config['output_dir'] = output_dir
        config['task_dir'] = task_dir
        config['task_config'] = task_config
        config['status_path'] = status_path

        # Update status to "running"
        _update_task_status(status_path, 'running')

        # Create manager for --task mode
        manager = ProcessManager(
            max_parallel=config.get('semaphore', 3),
            task_id=os.path.basename(task_dir),
            flow_name=flow_name,
            task_input=task_config.get('input', {}),
            agents_dir=agents_dir
        )
        manager.task_dir = task_dir
        manager.run_dir = task_dir
        manager.load_config(config, workflow_file=flow_path)

        print(f"\n[TASK] ID: {task_config.get('id')}")
        print(f"[TASK] Flow: {flow_name}")
        print(f"[TASK] Output: {output_dir}\n")

    elif args.config:
        config = load_config(args.config)
        agents_dir = getattr(args, 'agents_dir', '/server/agents')

        # Parse --input for config mode too
        task_input = {}
        if args.input:
            try:
                task_input = json.loads(args.input)
            except json.JSONDecodeError as e:
                print(f"[ERROR] Invalid JSON input: {e}")
                sys.exit(1)

        # Create manager for config mode
        manager = ProcessManager(
            max_parallel=config.get('semaphore', 3),
            resume_run_id=args.resume,
            agents_dir=agents_dir,
            task_input=task_input
        )
        manager.load_config(config, workflow_file=args.config)

    else:
        print("[ERROR] Provide config file, --flow, or --task")
        parser.print_help()
        sys.exit(1)

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
        manager._write_rein_log("SIGINT RECEIVED | graceful shutdown")
        manager._kill_remaining_processes("user interrupt")
        manager.running = False
        time.sleep(2)  # Wait for processes to finish
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Start stdin reader for pause/resume commands
    manager.start_stdin_reader()

    # Start Unix domain socket server for async commands
    manager.start_socket_server()

    # Run workflow
    if args.no_ui:
        # No UI mode - run workflow directly and wait
        manager.run_workflow()
    else:
        # Run workflow in background with Rich UI
        from rein.ui import ReinUI
        workflow_thread = threading.Thread(target=manager.run_workflow, daemon=True)
        workflow_thread.start()
        ui = ReinUI(manager)
        ui.run_live()

    # Exit when done
    manager.running = False
    sys.exit(0)

if __name__ == "__main__":
    main()
