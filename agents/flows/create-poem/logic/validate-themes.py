#!/usr/bin/env python3
"""
Validate-phase: Check that ideation block produced valid themes
"""
import json
import sys
import re

def extract_json_from_text(text):
    """Extract JSON object from text that may contain prose around it"""
    # Find the first { and matching }
    start = text.find('{')
    if start == -1:
        return None

    # Count braces to find the matching closing brace
    brace_count = 0
    for i, char in enumerate(text[start:], start=start):
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                try:
                    return json.loads(text[start:i+1])
                except:
                    return None
    return None

data_file = sys.argv[1]

try:
    with open(data_file) as f:
        envelope = json.load(f)

    # Unwrap the result (dog.py wraps output in {stage, result, timestamp})
    result_str = envelope.get('result', '')
    try:
        data = json.loads(result_str)
    except json.JSONDecodeError:
        # Try to extract JSON from mixed text
        data = extract_json_from_text(result_str)
        if not data:
            # If still no JSON, treat the envelope as the data
            data = envelope

    # Validate structure
    if 'themes' not in data:
        raise ValueError("Missing 'themes' field")

    if not isinstance(data['themes'], list):
        raise ValueError("'themes' must be a list")

    if len(data['themes']) == 0:
        raise ValueError("'themes' list is empty")

    # Validate each theme
    for i, theme in enumerate(data['themes']):
        if 'title' not in theme:
            raise ValueError(f"Theme {i} missing 'title'")
        if 'description' not in theme:
            raise ValueError(f"Theme {i} missing 'description'")

    print(f"[VALID] Ideation block produced {len(data['themes'])} themes")

except Exception as e:
    print(f"[ERROR] Ideation validation failed: {str(e)}")
    sys.exit(1)
