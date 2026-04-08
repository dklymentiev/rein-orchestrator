"""Block resolver: pure functions for flow control decisions.

Extracted from ProcessManager for testability and clarity.
All functions are pure -- they take explicit parameters and return results
without mutating any shared state.

Responsibilities:
- Flow control flag evaluation (skip_if_previous_failed, continue_if_failed)
- State machine next block resolution (next: string or list of if/else)
- Template condition evaluation ({{ result.X }}, comparisons)
- Dot-path resolution in result dicts
"""
import re
from typing import Optional, Callable, Any


def should_execute_block(block: dict, previous_failed: list) -> bool:
    """Check if block should be executed based on skip_if_previous_failed flag.

    skip_if_previous_failed=True  -> skip this block if any previous block failed
    skip_if_previous_failed=False -> continue executing even if previous failed (default)
    """
    skip_if_failed = block.get('skip_if_previous_failed', False)
    if previous_failed and skip_if_failed:
        return False
    return True


def should_continue_after_failure(block: dict, block_failed: bool) -> bool:
    """Check if workflow should continue after block failure.

    continue_if_failed=True (default): continue workflow even if block failed
    continue_if_failed=False: stop workflow on failure
    """
    if not block_failed:
        return True
    return block.get('continue_if_failed', True)


def resolve_path(path: str, data: dict) -> Any:
    """Resolve a dot-separated path like 'result.approved' in data dict."""
    parts = path.split('.')
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def evaluate_condition(
    expr: str,
    result_data: dict,
    log_fn: Optional[Callable[[str], None]] = None,
) -> bool:
    """Evaluate a condition expression against result data.

    Supports:
    - {{ result.approved }}              - truthy check
    - {{ result.status == 'approved' }}  - equality
    - {{ result.score > 0.8 }}           - comparison (>, <, >=, <=, !=)

    Returns False on parse/evaluation errors (safe default).
    """
    try:
        match = re.match(r'\{\{\s*(.+?)\s*\}\}', expr.strip())
        if not match:
            if log_fn:
                log_fn(f"CONDITION PARSE ERROR | no match: {expr}")
            return False

        inner_expr = match.group(1).strip()

        for op in ['==', '!=', '>=', '<=', '>', '<']:
            if op in inner_expr:
                parts = inner_expr.split(op, 1)
                if len(parts) == 2:
                    left = resolve_path(parts[0].strip(), result_data)
                    right_str = parts[1].strip().strip("'\"")

                    if isinstance(left, bool):
                        right = right_str.lower() in ('true', '1', 'yes')
                    elif isinstance(left, (int, float)):
                        try:
                            right = float(right_str)
                        except (ValueError, TypeError):
                            right = right_str
                    else:
                        right = right_str

                    if op == '==':   return left == right
                    elif op == '!=': return left != right
                    elif op == '>':  return left > right
                    elif op == '<':  return left < right
                    elif op == '>=': return left >= right
                    elif op == '<=': return left <= right

        # Truthy check
        value = resolve_path(inner_expr, result_data)
        return bool(value)
    except Exception as e:
        if log_fn:
            log_fn(f"CONDITION EVAL ERROR | {expr} | {str(e)}")
        return False


def evaluate_next_block(
    block: dict,
    result_data: dict,
    log_fn: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """Evaluate `next:` field and return target block name (state machine).

    Supports:
    - Simple string: next: "publish" -> always go to publish
    - Conditional list:
        next:
          - if: "{{ result.approved }}"
            goto: publish
          - else: revision
    """
    next_spec = block.get('next')
    if not next_spec:
        return None

    name = block.get('name') or block.get('stage', 'unknown')

    if isinstance(next_spec, str):
        if log_fn:
            log_fn(f"NEXT SIMPLE | {name} -> {next_spec}")
        return next_spec

    if isinstance(next_spec, list):
        for condition in next_spec:
            if 'else' in condition:
                goto = condition.get('goto') or condition.get('else')
                if log_fn:
                    log_fn(f"NEXT ELSE | {name} -> {goto}")
                return goto

            if 'if' in condition:
                condition_expr = condition['if']
                goto = condition.get('goto')
                if evaluate_condition(condition_expr, result_data, log_fn):
                    if log_fn:
                        log_fn(f"NEXT IF | {name} | condition={condition_expr} -> {goto}")
                    return goto

    return None
