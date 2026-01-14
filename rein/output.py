"""
Rein Output Helpers - Functions for formatting and saving workflow outputs
"""
import os
import json
import re
from datetime import datetime
from typing import Optional, Callable, List


def get_block_dir(task_dir: str, workflow_dir: str, block_name: str) -> str:
    """
    Get/create block directory: task/block/{inputs,outputs,logs}/

    Args:
        task_dir: Task directory path (or None)
        workflow_dir: Workflow directory path
        block_name: Name of the block

    Returns:
        Path to block directory
    """
    if task_dir:
        block_dir = os.path.join(task_dir, block_name)
    else:
        block_dir = os.path.join(workflow_dir, block_name)

    # Create block subdirectories
    os.makedirs(os.path.join(block_dir, "inputs"), exist_ok=True)
    os.makedirs(os.path.join(block_dir, "outputs"), exist_ok=True)
    os.makedirs(os.path.join(block_dir, "logs"), exist_ok=True)

    return block_dir


def get_output_dir(task_dir: str, workflow_dir: str, block_name: str = None) -> str:
    """
    Get the directory for saving block outputs

    Args:
        task_dir: Task directory path (or None)
        workflow_dir: Workflow directory path
        block_name: Name of the block (optional)

    Returns:
        Path to output directory
    """
    if block_name and task_dir:
        block_dir = get_block_dir(task_dir, workflow_dir, block_name)
        return os.path.join(block_dir, "outputs")
    elif task_dir:
        # Legacy: return task-level outputs
        outputs_dir = os.path.join(task_dir, "outputs")
        os.makedirs(outputs_dir, exist_ok=True)
        return outputs_dir
    else:
        return workflow_dir


def format_json_as_md(data: dict, level: int = 0) -> List[str]:
    """
    Format JSON dict as readable markdown sections with recursive handling

    Args:
        data: Dictionary to format
        level: Nesting level for headers

    Returns:
        List of markdown lines
    """
    lines = []
    if not isinstance(data, dict):
        lines.append(str(data))
        return lines

    for key, value in data.items():
        title = key.replace('_', ' ').title()

        # Use appropriate header level
        if level == 0:
            lines.append(f"## {title}")
        elif level == 1:
            lines.append(f"### {title}")
        else:
            lines.append(f"**{title}:**")
        lines.append("")

        if isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    # Format dict items nicely
                    item_title = item.get('name') or item.get('id') or item.get('gap') or item.get('idea') or f"Item {i+1}"
                    if isinstance(item_title, int):
                        item_title = f"#{item_title}"
                    lines.append(f"### {item_title}")
                    lines.append("")
                    for k, v in item.items():
                        if k in ('name', 'id'):
                            continue  # Already used as title
                        k_title = k.replace('_', ' ').title()
                        if isinstance(v, list):
                            lines.append(f"**{k_title}:**")
                            for sub_item in v:
                                lines.append(f"- {sub_item}")
                        elif isinstance(v, str) and len(v) > 100:
                            lines.append(f"**{k_title}:** {v}")
                        else:
                            lines.append(f"**{k_title}:** {v}")
                    lines.append("")
                elif isinstance(item, str) and len(item) > 100:
                    lines.append(f"- {item}")
                else:
                    lines.append(f"- {item}")
            lines.append("")
        elif isinstance(value, dict):
            # Recursively format nested dicts
            nested = format_json_as_md(value, level + 1)
            lines.extend(nested)
        elif isinstance(value, (int, float)):
            lines.append(str(value))
            lines.append("")
        else:
            lines.append(str(value))
            lines.append("")

    return lines


def save_readable_output(
    json_file: str,
    block_name: str,
    result: str,
    logger: Optional[Callable[[str], None]] = None
) -> bool:
    """
    Save human-readable MD version of block output

    Args:
        json_file: Path to the JSON file
        block_name: Name of the block
        result: Result content to save
        logger: Optional logging function

    Returns:
        True if saved successfully, False otherwise
    """
    log = logger or (lambda x: None)

    try:
        md_file = json_file.replace('.json', '.md')
        lines = [f"# {block_name}", "", f"*{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*", ""]

        # Try to extract JSON from markdown code blocks
        json_match = re.search(r'```json\s*\n(.*?)\n```', result, re.DOTALL)

        if json_match:
            # Has text + JSON block
            text_before = result[:json_match.start()].strip()
            json_str = json_match.group(1)
            text_after = result[json_match.end():].strip()

            if text_before:
                lines.append(text_before)
                lines.append("")

            # Parse and format JSON
            try:
                parsed = json.loads(json_str)
                lines.extend(format_json_as_md(parsed))
            except (json.JSONDecodeError, ValueError):
                lines.append(f"```json\n{json_str}\n```")

            if text_after:
                lines.append("")
                lines.append(text_after)
        else:
            # Try parsing as pure JSON
            try:
                parsed = json.loads(result)
                lines.extend(format_json_as_md(parsed))
            except (json.JSONDecodeError, ValueError):
                # Plain text - just add it
                lines.append(result)

        with open(md_file, 'w') as f:
            f.write("\n".join(lines))

        log(f"READABLE OUTPUT | {block_name} | saved={md_file}")
        return True

    except Exception as e:
        log(f"READABLE OUTPUT ERROR | {block_name} | {str(e)}")
        return False
