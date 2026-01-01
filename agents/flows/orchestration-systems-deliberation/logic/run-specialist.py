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


def substitute_placeholders(prompt: str, workflow_dir: Path) -> str:
    """Replace {{ file.json }} with actual file contents"""
    import re
    pattern = r'\{\{\s*(\w+\.json)\s*\}\}'

    def replacer(match):
        filename = match.group(1)
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


async def run_specialist(output_file: str):
    """Run specialist using claude-wrapper with real file access"""

    output_path = Path(output_file)
    workflow_dir = output_path.parent
    block_name = output_path.stem  # e.g., "prompt_engineer_initial"

    print(f"[INFO] Block: {block_name}")
    print(f"[INFO] Workflow dir: {workflow_dir}")

    # Load workflow config
    workflow_config = load_workflow_config(workflow_dir)
    if not workflow_config:
        raise Exception(f"No workflow YAML found in {workflow_dir}")

    # Get block config
    block = get_block_config(workflow_config, block_name)
    if not block:
        raise Exception(f"Block {block_name} not found in workflow")

    # Get prompt and substitute placeholders
    prompt_template = block.get('prompt', 'Analyze the systems')
    prompt = substitute_placeholders(prompt_template, workflow_dir)

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
    # Read output file path from stdin (dog.py passes it this way)
    output_file = sys.stdin.read().strip()

    if not output_file:
        print("[ERROR] No output file path provided via stdin")
        sys.exit(1)

    print(f"[START] run-specialist.py")
    print(f"[INFO] Output file: {output_file}")

    success = asyncio.run(run_specialist(output_file))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
