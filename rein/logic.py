"""
Rein Logic Runner - Execute logic scripts (Python/Shell) for workflow blocks
"""
import os
import json
import subprocess
from typing import Optional, Callable, Dict, Any, List


class LogicRunner:
    """Runner for workflow logic scripts"""

    def __init__(
        self,
        task_dir: str,
        workflow_dir: str,
        task_id: str = "",
        task_input: Optional[Dict] = None,
        logger: Optional[Callable[[str], None]] = None,
        timeout: int = 480  # 8 minutes default
    ):
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
        block_config: Optional[Dict] = None
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

        Returns:
            True if script succeeded, False otherwise
        """
        try:
            # Resolve relative path
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
                "block_config": block_config
            }
            context_json = json.dumps(context)

            self.logger(f"LOGIC RUN | {script_path} | output={output_file} | task={self.task_id}")

            # Run script based on type
            if script_path.endswith('.py'):
                result = subprocess.run(
                    ['python3', full_path],
                    input=context_json,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    cwd=self.task_dir
                )
            elif script_path.endswith('.sh'):
                result = subprocess.run(
                    ['bash', full_path],
                    input=context_json,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    cwd=self.task_dir
                )
            else:
                self.logger(f"LOGIC ERROR | unknown script type: {script_path}")
                return False

            # Log output
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        self.logger(f"LOGIC OUTPUT | {line}")

            if result.returncode != 0:
                if result.stderr:
                    for line in result.stderr.strip().split('\n'):
                        if line:
                            self.logger(f"LOGIC ERROR | {line}")
                return False

            return True

        except subprocess.TimeoutExpired:
            self.logger(f"LOGIC ERROR | timeout: {script_path}")
            return False
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
