#!/usr/bin/env python3
"""
Validate-phase: Check that ideation block produced valid themes.
Ensures the LLM output has the expected JSON structure before proceeding.
"""
import json
import sys


def extract_json_from_text(text):
    """Extract JSON object from text that may contain prose around it."""
    start = text.find('{')
    if start == -1:
        return None

    brace_count = 0
    for i, char in enumerate(text[start:], start=start):
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                try:
                    return json.loads(text[start:i+1])
                except json.JSONDecodeError:
                    return None
    return None


data_file = sys.argv[1]

try:
    with open(data_file) as f:
        envelope = json.load(f)

    # Unwrap the result envelope
    result_str = envelope.get('result', '')
    try:
        data = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        data = extract_json_from_text(result_str) if isinstance(result_str, str) else None
        if not data:
            data = envelope

    # Validate structure
    if 'themes' not in data:
        raise ValueError("Missing 'themes' field")

    if not isinstance(data['themes'], list):
        raise ValueError("'themes' must be a list")

    if len(data['themes']) == 0:
        raise ValueError("'themes' list is empty")

    for i, theme in enumerate(data['themes']):
        if 'title' not in theme:
            raise ValueError(f"Theme {i} missing 'title'")
        if 'description' not in theme:
            raise ValueError(f"Theme {i} missing 'description'")

    print(f"[VALID] Ideation block produced {len(data['themes'])} themes")

except Exception as e:
    print(f"[ERROR] Ideation validation failed: {str(e)}")
    sys.exit(1)
