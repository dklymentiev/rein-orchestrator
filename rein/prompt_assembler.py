"""Prompt assembly with placeholder substitution.

Extracted from ProcessManager.assemble_prompt. Handles:
- Specialist instruction loading
- {{ task.input.FIELD }} placeholders from task_input dict
- {{ block_name.json }} placeholders from block output files
- Team tone + specialist + block prompt concatenation
"""
import json
import os
import re
from typing import Callable, Dict, List, Optional


def substitute_task_inputs(
    prompt: str,
    task_input: Dict[str, any],
    log_fn: Callable[[str], None],
) -> str:
    """Substitute {{ task.input.FIELD }} placeholders with values from task_input.

    Dict/list values are JSON-serialized. Missing fields are left as-is
    (caller should check for unresolved placeholders).
    """
    if not task_input:
        return prompt
    pattern = r'\{\{\s*task\.input\.(\w+)\s*\}\}'
    for match in re.finditer(pattern, prompt):
        full_placeholder = match.group(0)
        field_name = match.group(1)
        if field_name in task_input:
            value = task_input[field_name]
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            prompt = prompt.replace(full_placeholder, str(value))
            log_fn(f"TASK INPUT SUBSTITUTED | {field_name} | value_len={len(str(value))}")
    return prompt


def resolve_file_placeholder(
    filename: str,
    task_dir: Optional[str],
    workflow_dir: Optional[str],
) -> Optional[str]:
    """Resolve {{ filename }} placeholder to a file path.

    Priority order:
    1. Block output by block name: task_dir/<block>/outputs/result.json (if filename = "block.json")
    2. save_as alias: task_dir/*/outputs/<filename> (custom save_as filename from any block)
    3. Task outputs: task_dir/outputs/filename
    4. Workflow directory: workflow_dir/filename (static data)
    """
    # 1. Block output by name (filename = "block_name.json")
    if task_dir and filename.endswith('.json'):
        block_name = filename[:-5]
        block_output = os.path.join(task_dir, block_name, "outputs", "result.json")
        if os.path.exists(block_output):
            return block_output

    # 2. save_as alias: search across all block output dirs (fix #1185)
    if task_dir and os.path.isdir(task_dir):
        for entry in os.listdir(task_dir):
            candidate = os.path.join(task_dir, entry, "outputs", filename)
            if os.path.isfile(candidate):
                return candidate

    # 3. Task outputs
    if task_dir:
        task_output_path = os.path.join(task_dir, "outputs", filename)
        if os.path.exists(task_output_path):
            return task_output_path

    # 4. Workflow directory
    if workflow_dir:
        workflow_path = os.path.join(workflow_dir, filename)
        if os.path.exists(workflow_path):
            return workflow_path

    return None


def substitute_file_placeholders(
    prompt: str,
    task_dir: Optional[str],
    workflow_dir: Optional[str],
    log_fn: Callable[[str], None],
) -> str:
    """Substitute {{ filename.json }} placeholders with file contents.

    Supports the result envelope pattern: if file contains {"result": "..."},
    tries to parse the inner result as JSON.
    """
    placeholder_matches = list(re.finditer(r'\{\{([^}]+)\}\}', prompt))

    for match in placeholder_matches:
        full_placeholder = match.group(0)
        filename = match.group(1).strip()

        # Skip task.input placeholders (handled separately)
        if filename.startswith('task.input.'):
            continue

        file_path = resolve_file_placeholder(filename, task_dir, workflow_dir)
        if not file_path:
            log_fn(f"FILE NOT FOUND | {filename} (checked block outputs, task outputs, workflow dir)")
            continue

        try:
            with open(file_path) as f:
                data = json.load(f)
                # Extract just data content if wrapped in envelope
                if isinstance(data, dict) and 'result' in data:
                    result_str = data.get('result', '')
                    try:
                        inner_data = json.loads(result_str)
                        data = inner_data
                    except (json.JSONDecodeError, ValueError, TypeError):
                        pass
                prompt = prompt.replace(full_placeholder, json.dumps(data, ensure_ascii=False))
                log_fn(f"FILE SUBSTITUTED | {filename} | from={file_path} | size={len(json.dumps(data))}")
        except Exception as e:
            log_fn(f"FILE SUBSTITUTE ERROR | {file_path} | {str(e)}")

    return prompt


def check_unresolved_inputs(prompt: str, task_input: Dict[str, any]) -> None:
    """Raise ValueError if any {{ task.input.X }} placeholders remain unresolved."""
    unresolved = re.findall(r'\{\{\s*task\.input\.(\w+)\s*\}\}', prompt)
    if unresolved:
        raise ValueError(
            f"Unresolved input placeholders: {set(unresolved)}. "
            f"Provided inputs: {list(task_input.keys())}"
        )


def extract_block_agents(block: dict) -> List[str]:
    """Extract agent list from block config (supports old `agents` list + new `specialist` single)."""
    agents = block.get('agents', []) or []
    if block.get('specialist'):
        agents = [block.get('specialist')]
    return agents


def build_final_prompt(team_tone: str, specialist_text: str, block_prompt: str) -> str:
    """Combine team tone + specialist instructions + block prompt into final prompt."""
    return f"{team_tone}\n\n{specialist_text}\n\n---\n\n{block_prompt}"
