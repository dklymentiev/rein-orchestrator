"""Routing engine: signal extraction and routing rule matching.

Extracted from ProcessManager._execute_block to improve testability.
The actual state mutation (cascade, completed set) remains in
ProcessManager because it requires tight coupling with threading state.

This module handles only the PURE parts of routing evaluation:
- Reading VERDICT signals from block result JSON
- Matching signals against routing rules
- Resolving target block name
"""
import json
import os
from typing import Dict, Optional, Set, Tuple


def read_result_text(save_file: str) -> str:
    """Read and stringify the result field from a block output JSON file."""
    if not os.path.exists(save_file):
        return ""
    try:
        with open(save_file) as f:
            saved_data = json.load(f)
        inner = saved_data.get('result', saved_data.get('response', ''))
        return inner if isinstance(inner, str) else json.dumps(inner)
    except Exception:
        return ""


def extract_verdict_signals(result_text: str) -> Set[str]:
    """Extract routing signals from result text.

    Looks for lines starting with 'VERDICT:' and maps verdict values to signals.

    Legacy aliases (preserved for backward compatibility):
        PASS, APPROVED -> 'needs-review'
        REVISE         -> 'revise'

    The raw verdict value is also emitted as a lowercase signal so workflows
    can define arbitrary custom signals:
        VERDICT: bounced  -> 'bounced'
        VERDICT: reshoot  -> 'reshoot'
        VERDICT: retry    -> 'retry'

    Returns a set of matched signal names.
    """
    signals: Set[str] = set()
    for line in result_text.upper().split('\n'):
        line = line.strip()
        if line.startswith('VERDICT:'):
            verdict = line.split(':', 1)[1].strip()
            if not verdict:
                continue
            # Legacy aliases
            if verdict == 'PASS' or verdict == 'APPROVED':
                signals.add('needs-review')
            elif verdict == 'REVISE':
                signals.add('revise')
            # Always emit the raw verdict as a lowercase custom signal
            signals.add(verdict.lower())
    return signals


def match_routing_rule(
    routing: Dict[str, str],
    signals: Set[str],
) -> Tuple[Optional[str], Optional[str]]:
    """Match signals against routing rules, with _default fallback.

    Args:
        routing: Block's routing dict, e.g. {'revise': 'fix', '_default': 'next'}
        signals: Set of detected signals from result

    Returns:
        Tuple of (next_block_name, matched_signal). Either may be None.
    """
    next_block_name: Optional[str] = None
    matched_signal: Optional[str] = None

    for signal in signals:
        if signal in routing:
            next_block_name = routing[signal]
            matched_signal = signal
            break

    if not next_block_name:
        next_block_name = routing.get('_default')
        matched_signal = '_default'

    return next_block_name, matched_signal


def parse_result_data(save_file: str) -> dict:
    """Parse block result for next:/if: condition evaluation.

    Returns a dict wrapping the inner result. Handles dict, JSON string, and
    plain string values. Used by state machine conditional `next:` logic.
    """
    if not os.path.exists(save_file):
        return {}
    try:
        with open(save_file) as f:
            saved_data = json.load(f)
    except Exception:
        return {}

    inner_result = saved_data.get('result', {})
    if isinstance(inner_result, dict):
        parsed_result = inner_result
    elif isinstance(inner_result, str):
        try:
            parsed_result = json.loads(inner_result)
        except (json.JSONDecodeError, ValueError):
            parsed_result = {'raw': inner_result}
    else:
        parsed_result = {'value': inner_result}

    return {'result': parsed_result, '_saved': saved_data}
