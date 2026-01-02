#!/usr/bin/env python3
"""
Generic pre-phase logic script for deliberation workflow.
Uses claude-wrapper in CLI mode to give Claude access to real files.

This script:
  1. Reads task context from stdin (JSON with task_input, outputs_dir, etc.)
  2. Reads block config from workflow YAML
  3. Substitutes {{ task.input.* }} and {{ file.json }} placeholders
  4. Calls claude-wrapper (CLI mode with file access)
  5. Saves result to the output file
"""

import asyncio
import sys
import os
import json
import yaml
import re
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


def substitute_task_input(prompt: str, task_input: dict) -> str:
    """Replace {{ task.input.fieldname }} with actual values"""
    if not task_input:
        return prompt

    pattern = r'\{\{\s*task\.input\.(\w+)\s*\}\}'

    def replacer(match):
        field_name = match.group(1)
        if field_name in task_input:
            value = task_input[field_name]
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False)
            return str(value)
        return match.group(0)  # Keep placeholder if field not found

    return re.sub(pattern, replacer, prompt)


def substitute_file_placeholders(prompt: str, outputs_dir: Path, workflow_dir: Path = None) -> str:
    """Replace {{ file.json }} with actual file contents"""
    pattern = r'\{\{\s*(\w+\.json)\s*\}\}'

    def replacer(match):
        filename = match.group(1)
        # Try outputs_dir first
        filepath = outputs_dir / filename
        if not filepath.exists() and workflow_dir:
            filepath = workflow_dir / filename

        if filepath.exists():
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    return data.get('result', json.dumps(data, indent=2, ensure_ascii=False))
            except:
                return f"[ERROR: Could not read {filename}]"
        return f"[File not found: {filename}]"

    return re.sub(pattern, replacer, prompt)


async def run_specialist(output_file: str, workflow_dir: str = None, outputs_dir: str = None,
                         task_id: str = None, task_input: dict = None):
    """Run specialist using claude-wrapper with real file access"""

    output_path = Path(output_file)

    # Use provided directories or fall back to inferring from output_path
    if outputs_dir:
        outputs_path = Path(outputs_dir)
    else:
        outputs_path = output_path.parent

    if workflow_dir:
        wf_dir = Path(workflow_dir)
    else:
        wf_dir = output_path.parent

    block_name = output_path.stem

    print(f"[INFO] Block: {block_name}")
    print(f"[INFO] Workflow dir: {wf_dir}")
    print(f"[INFO] Outputs dir: {outputs_path}")
    if task_id:
        print(f"[INFO] Task ID: {task_id}")
    if task_input:
        print(f"[INFO] Task input keys: {list(task_input.keys())}")

    # Load workflow config
    workflow_config = load_workflow_config(wf_dir)
    if not workflow_config:
        raise Exception(f"No workflow YAML found in {wf_dir}")

    # Get block config
    block = get_block_config(workflow_config, block_name)
    if not block:
        raise Exception(f"Block {block_name} not found in workflow")

    # Get prompt template
    prompt_template = block.get('prompt', 'Analyze the topic.')

    # Step 1: Substitute task.input placeholders
    prompt = substitute_task_input(prompt_template, task_input)
    print(f"[INFO] After task.input substitution: {len(prompt)} chars")

    # Step 2: Substitute file placeholders (dependencies)
    prompt = substitute_file_placeholders(prompt, outputs_path, wf_dir)
    print(f"[INFO] After file substitution: {len(prompt)} chars")

    # Build full prompt (generic - no hardcoded instructions)
    full_prompt = f"""{prompt}

IMPORTANT: If the task mentions analyzing code or systems, you have access to read files on the server.
Use the Read tool to examine actual source code when relevant.

Return your analysis as valid JSON matching the requested format.
"""

    print(f"[INFO] Final prompt length: {len(full_prompt)} chars")
    print(f"[INFO] First 500 chars: {full_prompt[:500]}")

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
    # Read JSON context from stdin (dog.py passes task context)
    stdin_data = sys.stdin.read().strip()

    if not stdin_data:
        print("[ERROR] No input provided via stdin")
        sys.exit(1)

    # Parse JSON context
    output_file = None
    workflow_dir = None
    outputs_dir = None
    task_id = None
    task_input = None

    try:
        context = json.loads(stdin_data)
        output_file = context.get('output_file')
        workflow_dir = context.get('workflow_dir')
        outputs_dir = context.get('outputs_dir')
        task_id = context.get('task_id')
        task_input = context.get('task_input', {})
        print("[INFO] Received JSON context from dog.py")
    except json.JSONDecodeError:
        # Backward compatibility: plain file path
        output_file = stdin_data
        print("[INFO] Received plain file path (legacy mode)")

    if not output_file:
        print("[ERROR] No output file path in context")
        sys.exit(1)

    print(f"[START] run-specialist.py (generic deliberation)")
    print(f"[INFO] Output file: {output_file}")

    success = asyncio.run(run_specialist(output_file, workflow_dir, outputs_dir, task_id, task_input))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
