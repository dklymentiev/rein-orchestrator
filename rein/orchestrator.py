"""
Rein Orchestrator - ProcessManager for workflow execution.

The ProcessManager coordinates block execution with dependency tracking,
semaphore-based parallelism, prompt assembly, and state persistence.
"""
import os
import sys
import yaml
import json
import subprocess
import time
import signal
import threading
import re
import uuid
import socket
import select
from dataclasses import asdict
from typing import List, Dict, Optional, Set
from datetime import datetime
from pathlib import Path
import psutil
from rich.console import Console
from rich.table import Table
from rich.live import Live

# Import refactored modules
from rein import (
    Process, ConfigLoader, LogicRunner, ReinState,
    format_json_as_md, save_readable_output, get_block_dir, get_output_dir
)
from rein.providers import create_provider
from rein.providers.base import UsageStats
from rein.tasks import update_task_status as _update_task_status
from rein.tasks import save_task_to_memory as _save_task_to_memory
from rein.log import get_logger, get_console

logger = get_logger(__name__)
console = get_console()

# Import validation engine (Phase 1: Schema validation)
try:
    from models.validator import ValidationEngine
    HAS_VALIDATION = True
except ImportError:
    import warnings
    warnings.warn("models.validator not found - workflow schema validation disabled", stacklevel=2)
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
        from rein.config import DEFAULT_AGENTS_DIR
        self.agents_dir = agents_dir or DEFAULT_AGENTS_DIR

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
            runs_base = os.environ.get("REIN_RUNS_DIR", "/tmp/rein-runs")
            self.task_dir = f"{runs_base}/run-{resume_run_id}"
            self.guid = resume_run_id
        else:
            runs_base = os.environ.get("REIN_RUNS_DIR", "/tmp/rein-runs")
            self.task_dir = f"{runs_base}/run-{timestamp}"
            self.guid = timestamp

        self.run_dir = self.task_dir  # V3: run_dir = task_dir always

        # V3: Create all task directories
        self.log_dir = os.path.join(self.run_dir, "logs")
        self.rein_log_file = os.path.join(self.run_dir, "rein.log")
        self.db_path = os.path.join(self.run_dir, "state", "rein.db")
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(os.path.join(self.task_dir, "state"), exist_ok=True)

        # Initialize state with unique DB for this run (or reuse existing DB if resuming)
        # Auto-detect resume mode if DB exists with data (allows --task to resume properly)
        db_exists = os.path.exists(self.db_path)
        should_resume = bool(resume_run_id) or db_exists
        self.state = ReinState(self.db_path, resume=should_resume)

        # Initialize refactored components
        self.config_loader = ConfigLoader(agents_dir=self.agents_dir, logger=self._write_rein_log)
        # Provider will be initialized when workflow config is loaded (see _init_provider)
        self._provider = None

        # Cost/token tracking
        self._block_usage: Dict[str, UsageStats] = {}  # block_name -> usage
        self._total_usage = UsageStats()  # Accumulated totals

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
            logger.error("Log write failed: %s", e)

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

        # Initialize LLM provider from workflow config
        self._init_provider(config)

        self._write_rein_log(f"CONFIG LOADED | {len(self.all_blocks)} blocks | timeout={self.timeout}s | workflow_dir={self.workflow_dir}")

        # Pre-flight validation (Phase 1: Schema validation)
        if HAS_VALIDATION and workflow_file:
            self._run_preflight_validation(workflow_file)

        # Input validation (v2.6.0: declarative inputs)
        self._validate_task_inputs(config)

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
                console.info("")
                console.info("[VALIDATE] Workflow: %s", result.metadata.get('name'))
                console.info("[VALIDATE] Team: %s", result.metadata.get('team'))
                console.info("[VALIDATE] Schema Version: %s", result.metadata.get('schema_version'))
                console.info("[VALIDATE] Blocks: %s", result.metadata.get('blocks_count'))
                console.info("[VALIDATE] Execution Phases: %s", result.metadata.get('phases'))
                console.info("[VALIDATE] Flow Control Blocks: %s", result.metadata.get('flow_control_blocks'))
                console.info("[VALIDATE] Status: OK\n")
            else:
                self._write_rein_log(f"VALIDATE FAILED | errors={len(result.errors)} | warnings={len(result.warnings)}")
                console.error("\n[ERROR] Workflow validation failed!")
                console.error(result.format_report())
                console.info("")
                sys.exit(1)

            if result.warnings:
                logger.warning("%d validation warnings:", len(result.warnings))
                for warning in result.warnings:
                    logger.warning("  - %s: %s", warning.field, warning.message)

        except Exception as e:
            self._write_rein_log(f"VALIDATE ERROR | {str(e)}")
            logger.warning("Validation engine error (continuing anyway): %s", e)

    def _validate_task_inputs(self, config: dict):
        """Validate task inputs against declarative inputs: section (v2.6.0).

        - If no inputs: section, skip entirely (backward compat).
        - For each declared required field: check if present in self.task_input.
        - For optional fields with default: inject into self.task_input if missing.
        - Log warning for extra (undeclared) inputs.
        - On errors: print, log, sys.exit(1).
        """
        inputs_spec = config.get('inputs')
        if not inputs_spec:
            return  # No inputs declared - backward compatible

        errors = []
        declared = set(inputs_spec.keys())
        provided = set(self.task_input.keys())

        for field_name, field_config in inputs_spec.items():
            # field_config can be a dict (from YAML) or InputFieldConfig (from models.workflow)
            if isinstance(field_config, dict):
                is_required = field_config.get('required', True)
                default_val = field_config.get('default')
            else:
                is_required = field_config.required
                default_val = field_config.default

            if field_name not in self.task_input:
                if is_required:
                    desc = ""
                    if isinstance(field_config, dict):
                        desc = field_config.get('description', '')
                    elif hasattr(field_config, 'description'):
                        desc = field_config.description or ''
                    hint = f" ({desc})" if desc else ""
                    errors.append(f"  - '{field_name}'{hint}")
                elif default_val is not None:
                    # Inject default value
                    self.task_input[field_name] = default_val
                    self._write_rein_log(f"INPUT DEFAULT | {field_name} = {default_val}")

        # Warn about extra (undeclared) inputs
        extra = provided - declared
        if extra:
            self._write_rein_log(f"INPUT WARNING | Extra undeclared inputs: {sorted(extra)}")
            logger.warning("Extra inputs not declared in workflow: %s", sorted(extra))

        if errors:
            workflow_name = config.get('name', 'unknown')
            msg = (
                f"\n[ERROR] Missing required inputs for workflow '{workflow_name}':\n"
                + "\n".join(errors)
                + f"\n\nDeclared inputs: {sorted(declared)}"
                + f"\nProvided inputs: {sorted(provided)}"
                + "\n\nProvide inputs via --input '{\"field\": \"value\"}' or task.input.json\n"
            )
            console.error(msg)
            missing_names = [e.strip().lstrip("- '").split("'")[0] for e in errors]
            self._write_rein_log(f"INPUT VALIDATION FAILED | missing: {missing_names}")
            sys.exit(1)

        self._write_rein_log(f"INPUT VALIDATION OK | declared={sorted(declared)} | provided={sorted(provided)}")

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

                # Try to resolve file path in order of priority
                file_path = None

                # 1. Block output: {{ block_name.json }} -> task_dir/block_name/outputs/result.json
                if self.task_dir and filename.endswith('.json'):
                    block_name = filename[:-5]  # Remove .json
                    block_output = os.path.join(self.task_dir, block_name, "outputs", "result.json")
                    if os.path.exists(block_output):
                        file_path = block_output
                        self._write_rein_log(f"BLOCK OUTPUT FOUND | {block_name} | {block_output}")

                # 2. Task outputs: task_dir/outputs/filename
                if not file_path and self.task_dir:
                    task_output_path = os.path.join(self.task_dir, "outputs", filename)
                    if os.path.exists(task_output_path):
                        file_path = task_output_path

                # 3. Workflow directory: workflow_dir/filename (for static data)
                if not file_path and self.workflow_dir:
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
                    self._write_rein_log(f"FILE NOT FOUND | {filename} (checked block outputs, task outputs, workflow dir)")

            # Safety net: detect unresolved {{ task.input.* }} placeholders
            unresolved = re.findall(r'\{\{\s*task\.input\.(\w+)\s*\}\}', prompt)
            if unresolved:
                raise ValueError(
                    f"Unresolved input placeholders: {set(unresolved)}. "
                    f"Provided inputs: {list(self.task_input.keys())}"
                )

            # Build final prompt
            full_prompt = f"""{team_tone}

{specialist_text}

---

{prompt}"""
            # Debug logging
            self._write_rein_log(f"ASSEMBLED PROMPT | len={len(full_prompt)} | first_200={full_prompt[:200]}")
            return full_prompt
        except ValueError:
            raise  # Propagate validation errors (unresolved placeholders)
        except Exception as e:
            self._write_rein_log(f"PROMPT ASSEMBLY ERROR | {str(e)}")
            return ""

    def _init_provider(self, workflow_config: dict):
        """Initialize LLM provider from workflow config or environment."""
        if self._provider is not None:
            return  # Already initialized

        provider_cfg = self.config_loader.get_provider_config(workflow_config)
        self._write_rein_log(f"PROVIDER CONFIG | {provider_cfg}")

        try:
            self._provider = create_provider(
                logger=self._write_rein_log,
                **provider_cfg,
            )
            self._write_rein_log(f"PROVIDER READY | {self._provider.provider_name} | model={self._provider.model}")
        except ValueError:
            raise

    def call_claude(self, prompt: str, stage: str) -> str:
        """Call LLM provider and track usage (backward-compatible name).

        Returns only the text; usage is accumulated internally.
        """
        if self._provider is None:
            # Late init with empty config - will auto-detect from env
            self._init_provider({})

        text, usage = self._provider.call(prompt, stage)
        self._accumulate_usage(stage, usage)
        return text

    def _accumulate_usage(self, block_name: str, usage: UsageStats):
        """Accumulate per-block and total usage stats."""
        self._block_usage[block_name] = usage
        self._total_usage.input_tokens += usage.input_tokens
        self._total_usage.output_tokens += usage.output_tokens
        self._total_usage.cost += usage.cost
        self._total_usage.duration_ms += usage.duration_ms
        if not self._total_usage.provider:
            self._total_usage.provider = usage.provider
            self._total_usage.model = usage.model

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

    def _get_dependents_map(self) -> Dict[str, List[str]]:
        """Build reverse dependency graph: {block -> [blocks that depend on it]}"""
        dependents: Dict[str, List[str]] = {}
        for block in self.all_blocks:
            name = block.get('name') or block.get('stage', 'unknown')
            for dep in block.get('depends_on', []):
                if dep not in dependents:
                    dependents[dep] = []
                dependents[dep].append(name)
        return dependents

    def _cascade_invalidation(self, failed_blocks: Set[str], dependents_map: Dict[str, List[str]]) -> Set[str]:
        """BFS from failed blocks through dependents. Returns full set needing re-run."""
        needs_rerun = set(failed_blocks)
        queue = list(failed_blocks)
        while queue:
            current = queue.pop(0)
            for downstream in dependents_map.get(current, []):
                if downstream not in needs_rerun:
                    needs_rerun.add(downstream)
                    queue.append(downstream)
                    self._write_rein_log(f"CASCADE | {downstream} | invalidated (depends on {current})")
        return needs_rerun

    def _clean_block_outputs(self, block_name: str):
        """Delete output files for a block to prevent stale data."""
        import shutil
        outputs_dir = os.path.join(self.run_dir, block_name, "outputs")
        if os.path.exists(outputs_dir):
            shutil.rmtree(outputs_dir)
            self._write_rein_log(f"CLEANUP | {block_name} | removed outputs")

    def _initialize_all_processes(self):
        """Initialize all processes in DB with 'waiting' status (or restore existing)"""
        # First, load existing processes from DB to check for completed blocks
        existing_status = {}
        try:
            for db_proc in self.state.get_all_processes():
                existing_status[db_proc.name] = db_proc.status
        except Exception:
            pass

        # Cascade invalidation: find failed/running blocks and their downstream dependents
        needs_rerun: Set[str] = set()
        failed_blocks = {name for name, status in existing_status.items() if status in ("failed", "running")}
        if failed_blocks:
            dependents_map = self._get_dependents_map()
            needs_rerun = self._cascade_invalidation(failed_blocks, dependents_map)
            self._write_rein_log(f"RESUME | {len(failed_blocks)} failed/running blocks, {len(needs_rerun)} total to re-run")
            # Clean outputs for all invalidated blocks
            for block_name in needs_rerun:
                self._clean_block_outputs(block_name)

        # First pass - calculate phases
        block_phases: Dict[str, int] = {}
        for block in self.all_blocks:
            # Support both 'name' (old) and 'stage' (new Phase 2.5)
            name = block.get('name') or block.get('stage', 'unknown')
            depends_on = block.get('depends_on', [])
            phase = self._calculate_phase(depends_on, block_phases)
            block_phases[name] = phase

        # Second pass - create processes with phases (skip if already done)
        restored_count = 0
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

            # Check if block already completed and not invalidated - skip reinitializing
            prev_status = existing_status.get(name)
            if prev_status == "done" and name not in needs_rerun:
                self._write_rein_log(f"RESUME SKIP | {name} | already done")
                self.completed.add(name)
                restored_count += 1
                # Still need to track the process in memory
                process = Process(
                    pid=None,
                    name=name,
                    status="done",
                    start_time=time.time(),
                    command=command,
                    uid=uid,
                    depends_on=depends_on,
                    progress=100,
                    phase=phase,
                    blocking_pause=blocking_pause,
                    agent=agent,
                    next_spec=next_spec,
                    max_runs=max_runs
                )
                with self.lock:
                    self.processes[uid] = process
                    self.block_configs[name] = block
                continue  # Don't save to DB - keep existing record

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

        if restored_count > 0:
            self._write_rein_log(f"RESUME | Restored {restored_count} completed blocks from previous run")

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
        """Check if block should be executed based on skip_if_previous_failed flag

        skip_if_previous_failed=True  -> skip this block if any previous block failed
        skip_if_previous_failed=False -> continue executing even if previous failed (default)
        """
        skip_if_failed = block.get('skip_if_previous_failed', False)

        if previous_failed and skip_if_failed:
            # There were failures and this block SHOULD skip-on-failure
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

        # Skip if block already completed (resume mode)
        if name in self.completed:
            self._write_rein_log(f"SPAWN SKIP | {name} | already completed (resume)")
            return "skipped"

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
            self._write_rein_log(f"BLOCK SKIPPED | {name} | skip_if_previous_failed=true and failures detected")
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

        # Event marker for WebSocket broadcast (must be stdout for daemon parsing)
        console.info("[BLOCK_START] task=%s block=%s", self.task_id, name)

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

                    import shlex
                    proc = subprocess.Popen(
                        shlex.split(command),
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
                block_usage = self._block_usage.get(name)
                save_data = {
                    "stage": name,
                    "result": result,
                    "timestamp": datetime.now().isoformat()
                }
                if block_usage:
                    save_data["usage"] = block_usage.to_dict()
                with open(save_file, 'w') as f:
                    json.dump(save_data, f, indent=2, ensure_ascii=False)

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

            # Event marker for WebSocket broadcast (must be stdout for daemon parsing)
            console.info("[BLOCK_DONE] task=%s block=%s", self.task_id, name)

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

            # Add usage/cost data to summary
            if self._total_usage.total_tokens > 0:
                summary["usage"] = self._total_usage.to_dict()
                summary["block_usage"] = {
                    name: u.to_dict() for name, u in self._block_usage.items()
                }

            # Save metadata
            with open(os.path.join(self.run_dir, "metadata.json"), 'w') as f:
                json.dump(self.metadata, f, indent=2)

            # Save summary
            with open(os.path.join(self.run_dir, "summary.json"), 'w') as f:
                json.dump(summary, f, indent=2)

            # Log completion
            self._write_rein_log(f"REIN FINISHED | completed={completed} | failed={failed} | total={len(self.processes)}")

            # Log cost summary
            if self._total_usage.total_tokens > 0:
                cost_line = (
                    f"[COST] Total: ${self._total_usage.cost:.4f} | "
                    f"Tokens: {self._total_usage.total_tokens:,} "
                    f"(in:{self._total_usage.input_tokens:,} out:{self._total_usage.output_tokens:,}) | "
                    f"Provider: {self._total_usage.provider} | Model: {self._total_usage.model}"
                )
                self._write_rein_log(cost_line)
                console.info(cost_line)

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

            # Find the final result file (last block by phase)
            final_result = None
            if self.all_blocks:
                last_block = self.all_blocks[-1]
                last_name = last_block.get('name') or last_block.get('stage', '')
                candidate = os.path.join(self.task_dir, last_name, "outputs", "result.json")
                if os.path.exists(candidate):
                    final_result = candidate

            console.info("\n[OK] Run completed. Logs saved to: %s", self.run_dir)
            if final_result:
                console.info("[OK] Final result: %s", final_result)
                # Store for deferred printing (after UI stops)
                self._final_result_path = final_result
            if output_dir:
                console.info("[OK] Results saved to: %s", output_dir)
        except Exception as e:
            logger.error("Error saving run summary: %s", e)
            self._write_rein_log(f"FINALIZE ERROR | {str(e)}")

    def _print_final_result(self):
        """Print final result to stdout (called after UI stops)"""
        final_result = getattr(self, '_final_result_path', None)
        if not final_result or not self.config.get('print_final', False):
            return
        try:
            with open(final_result) as f:
                final_data = json.load(f)
            final_text = final_data.get('result', '')
            if final_text:
                print()
                print("=" * 60)
                print("FINAL RESULT")
                print("=" * 60)
                print(final_text[:5000])
                if len(final_text) > 5000:
                    print(f"\n... [truncated, see {final_result}]")
                print("=" * 60)
        except Exception:
            pass

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

