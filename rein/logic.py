"""
Rein Logic Runner - Execute logic scripts (Python/Shell) for workflow blocks
"""

import json
import os
import re
import signal
import subprocess
from typing import Callable, Dict, List, Optional

# linux_user must be a safe username: alphanumeric, hyphens, underscores
SAFE_LINUX_USER = re.compile(r"^[a-zA-Z0-9_-]+$")


class LogicRunner:
    """Runner for workflow logic scripts"""

    def __init__(
        self,
        task_dir: str,
        workflow_dir: str,
        task_id: str = "",
        task_input: Optional[Dict] = None,
        logger: Optional[Callable[[str], None]] = None,
        timeout: int = 480,  # 8 minutes default
        children=None,  # rein.children.ChildRegistry: where started scripts are recorded
    ):
        self.children = children
        self.task_dir = task_dir
        self.workflow_dir = workflow_dir
        self.task_id = task_id
        self.task_input = task_input or {}
        self.logger = logger or (lambda x: None)
        self.timeout = timeout

    def run(
        self,
        script_path: str,
        output_file: str,
        block_name: Optional[str] = None,
        block_dir: Optional[str] = None,
        input_dir: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        block_config: Optional[Dict] = None,
        linux_user: Optional[str] = None,
        run_count: int = 0,
        timeout_override: Optional[int] = None,
        no_timeout: bool = False,
    ) -> bool:
        """
        Run logic script (Python or Shell)

        Args:
            script_path: Relative path to script from workflow_dir
            output_file: Path where script should write output
            block_name: Name of the block running this script
            block_dir: Block directory (task_dir/block_name/)
            input_dir: Input directory for dependencies
            depends_on: List of dependency block names
            block_config: Full block configuration dict
            timeout_override: The block's own `timeout`, instead of the default
            no_timeout: The script has no limit of its own; the block's time
                budget is what stops it

        Returns:
            True if script succeeded, False otherwise
        """
        try:
            # Resolve relative path against workflow_dir. Containment is
            # not enforced here -- logic scripts are trusted per the
            # documented trust model (see SECURITY.md "Workflow YAML is
            # trusted input"). A workflow that references ../lib/helper.py
            # or ../../shared/util.sh is an accepted pattern for sharing
            # helpers between flows under the same agents_dir.
            full_path = os.path.join(self.workflow_dir, script_path)

            if not os.path.exists(full_path):
                self.logger(f"LOGIC ERROR | script not found: {full_path}")
                return False

            # Build context for script
            context = {
                "output_file": output_file,
                "workflow_dir": self.workflow_dir,
                "task_dir": self.task_dir,
                "task_id": self.task_id,
                "task_input": self.task_input,
                "block_dir": block_dir,
                "outputs_dir": os.path.join(block_dir, "outputs") if block_dir else self.task_dir,
                "input_dir": input_dir,
                "depends_on": depends_on or [],
                "block_config": block_config,
                "run_count": run_count,
            }
            context_json = json.dumps(context)

            self.logger(f"LOGIC RUN | {script_path} | output={output_file} | task={self.task_id}")

            # Build command with optional sudo -u for linux_user isolation
            if script_path.endswith(".py"):
                cmd = ["python3", full_path]
            elif script_path.endswith(".sh"):
                cmd = ["bash", full_path]
            else:
                self.logger(f"LOGIC ERROR | unknown script type: {script_path}")
                return False

            if linux_user:
                if not SAFE_LINUX_USER.match(linux_user):
                    self.logger(f"LOGIC ERROR | unsafe linux_user rejected: {linux_user}")
                    return False
                if linux_user == "root":
                    self.logger("LOGIC ERROR | sudo to root is forbidden")
                    return False
                cmd = ["sudo", "-u", linux_user] + cmd
                self.logger(f"LOGIC SUDO | running as {linux_user}")

            # Run script (use block-level timeout_override if provided)
            if no_timeout:
                effective_timeout = None
            else:
                effective_timeout = timeout_override if timeout_override else self.timeout

            # The script gets a session of its own, so that it can be stopped
            # together with everything it started, and it is recorded, so that
            # whoever stops the block (a time budget, a step that gives up
            # waiting) can find it.
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self.task_dir,
                start_new_session=True,
            )
            if self.children:
                self.children.started(block_name, proc)
            try:
                try:
                    stdout, stderr = proc.communicate(context_json, timeout=effective_timeout)
                except subprocess.TimeoutExpired:
                    self.logger(f"LOGIC ERROR | timeout after {effective_timeout}s: {script_path}")
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        proc.kill()
                    proc.communicate()
                    return False
            finally:
                if self.children:
                    self.children.finished(proc)

            # Log output
            if stdout:
                for line in stdout.strip().split("\n"):
                    if line:
                        self.logger(f"LOGIC OUTPUT | {line}")

            if proc.returncode != 0:
                if stderr:
                    for line in stderr.strip().split("\n"):
                        if line:
                            self.logger(f"LOGIC ERROR | {line}")
                if proc.returncode < 0:
                    self.logger(f"LOGIC ERROR | stopped by signal {-proc.returncode}: {script_path}")
                return False

            return True

        except Exception as e:
            self.logger(f"LOGIC ERROR | {str(e)}")
            return False

    def prepare_input_dir(self, block_name: str, depends_on: List[str]) -> str:
        """
        Prepare input directory for block, logging dependencies

        Args:
            block_name: Name of the block
            depends_on: List of dependency block names

        Returns:
            Path to input directory
        """
        block_dir = os.path.join(self.task_dir, block_name)
        input_dir = os.path.join(block_dir, "inputs")
        os.makedirs(input_dir, exist_ok=True)

        # Log dependencies for debugging
        for dep in depends_on:
            dep_output = os.path.join(self.task_dir, dep, "outputs", "result.json")
            if os.path.exists(dep_output):
                self.logger(f"INPUT DEP | {block_name} <- {dep}/outputs/result.json")
            else:
                self.logger(f"INPUT WARN | {block_name} | dependency not ready: {dep}")

        return input_dir
