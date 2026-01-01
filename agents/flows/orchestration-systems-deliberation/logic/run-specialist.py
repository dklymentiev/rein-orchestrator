#!/usr/bin/env python3
"""
Pre-phase logic script for deliberation workflow.
Uses claude-wrapper in CLI mode to give Claude access to real files.

Usage: Called by dog.py with output file path via stdin

dog.py passes:
  - stdin: path to output JSON file (e.g., /path/to/prompt_engineer_initial.json)

This script:
  1. Reads block config from workflow YAML
  2. Builds prompt with dependency substitution
  3. Calls claude-wrapper (CLI mode with file access)
  4. Saves result to the output file
"""

import asyncio
import sys
import os
import json
import yaml
from pathlib import Path
from datetime import datetime

# Add claude-wrapper to path
sys.path.insert(0, '/server/scripts/claude-wrapper')

from claude_wrapper import ClaudeWrapper


def load_workflow_config(workflow_dir: Path):
    """Load workflow YAML config"""
    yaml_files = list(workflow_dir.glob("*.yaml"))
    if not yaml_files:
        return None
    with open(yaml_files[0]) as f:
        return yaml.safe_load(f)


def get_block_config(workflow_config: dict, block_name: str) -> dict:
    """Get block configuration by name"""
    for block in workflow_config.get('blocks', []):
        if block.get('name') == block_name:
            return block
    return {}


def substitute_placeholders(prompt: str, outputs_dir: Path, workflow_dir: Path = None) -> str:
    """Replace {{ file.json }} with actual file contents

    REFACTOR: First looks in outputs_dir (task outputs), then fallback to workflow_dir
    """
    import re
    pattern = r'\{\{\s*(\w+\.json)\s*\}\}'

    def replacer(match):
        filename = match.group(1)
        # Try outputs_dir first (REFACTOR: task outputs)
        filepath = outputs_dir / filename
        if not filepath.exists() and workflow_dir:
            filepath = workflow_dir / filename

        if filepath.exists():
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    return data.get('result', json.dumps(data, indent=2))
            except:
                return f"[ERROR: Could not read {filename}]"
        return f"[File not found: {filename}]"

    return re.sub(pattern, replacer, prompt)


async def run_specialist(output_file: str, workflow_dir: str = None, outputs_dir: str = None, task_id: str = None):
    """Run specialist using claude-wrapper with real file access

    REFACTOR: Now accepts task context for proper output directory handling
    """

    output_path = Path(output_file)

    # REFACTOR: Use provided directories or fall back to inferring from output_path
    if outputs_dir:
        outputs_path = Path(outputs_dir)
    else:
        outputs_path = output_path.parent

    if workflow_dir:
        wf_dir = Path(workflow_dir)
    else:
        wf_dir = output_path.parent

    block_name = output_path.stem  # e.g., "prompt_engineer_initial"

    print(f"[INFO] Block: {block_name}")
    print(f"[INFO] Workflow dir: {wf_dir}")
    print(f"[INFO] Outputs dir: {outputs_path}")
    if task_id:
        print(f"[INFO] Task ID: {task_id}")

    # Load workflow config
    workflow_config = load_workflow_config(wf_dir)
    if not workflow_config:
        raise Exception(f"No workflow YAML found in {wf_dir}")

    # Get block config
    block = get_block_config(workflow_config, block_name)
    if not block:
        raise Exception(f"Block {block_name} not found in workflow")

    # Get prompt and substitute placeholders (REFACTOR: use outputs_dir for dependencies)
    prompt_template = block.get('prompt', 'Analyze the systems')
    prompt = substitute_placeholders(prompt_template, outputs_path, wf_dir)

    # Build full prompt with file access instructions
    full_prompt = f"""You are a specialist analyzing orchestration systems.

{prompt}

IMPORTANT: You have access to read files on the server. The relevant project files are:
- /server/scripts/agent-pm2-dog/ (Dog orchestrator - Python, 500+ lines)
- /server/agents/conductor/ (Conductor orchestrator - shell scripts)

Please READ the actual source code files to provide REAL analysis based on the code, not generic assumptions.

For Dog, read: /server/scripts/agent-pm2-dog/dog.py
For Conductor, read: /server/agents/conductor/conductor.sh

Return your analysis as valid JSON matching the requested format.
"""

    print(f"[INFO] Prompt length: {len(full_prompt)} chars")

    # Create wrapper in CLI mode (has file access)
    wrapper = ClaudeWrapper(
        mode="cli",
        model="sonnet",
        timeout=300,
    )

    try:
        print("[INFO] Initializing claude-wrapper...")
        await wrapper.initialize()

        print("[INFO] Calling Claude CLI...")
        response = await wrapper.call(full_prompt)

        # Save result
        result = {
            "stage": block_name,
            "result": response,
            "timestamp": datetime.now().isoformat()
        }

        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"[OK] Saved to {output_file}")
        print(f"[INFO] Response length: {len(response)} chars")

        return True

    except Exception as e:
        print(f"[ERROR] {e}")
        # Save error result
        result = {
            "stage": block_name,
            "result": f"ERROR: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        return False

    finally:
        await wrapper.shutdown()


def main():
    # REFACTOR: Read JSON context from stdin (dog.py passes task context)
    # Backward compatible: also works with plain file path
    stdin_data = sys.stdin.read().strip()

    if not stdin_data:
        print("[ERROR] No input provided via stdin")
        sys.exit(1)

    # Try to parse as JSON context
    output_file = None
    workflow_dir = None
    outputs_dir = None
    task_id = None

    try:
        context = json.loads(stdin_data)
        output_file = context.get('output_file')
        workflow_dir = context.get('workflow_dir')
        outputs_dir = context.get('outputs_dir')
        task_id = context.get('task_id')
        print("[INFO] Received JSON context from dog.py")
    except json.JSONDecodeError:
        # Backward compatibility: plain file path
        output_file = stdin_data
        print("[INFO] Received plain file path (legacy mode)")

    if not output_file:
        print("[ERROR] No output file path in context")
        sys.exit(1)

    print(f"[START] run-specialist.py")
    print(f"[INFO] Output file: {output_file}")

    success = asyncio.run(run_specialist(output_file, workflow_dir, outputs_dir, task_id))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
