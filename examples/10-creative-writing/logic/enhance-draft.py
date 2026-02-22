#!/usr/bin/env python3
"""
Post-phase: Enhance draft with metadata and formatting.
Adds line count, word count, and character count to the draft output.
"""
import json
import sys
from datetime import datetime


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

    # Validate draft structure
    if 'poem' not in data:
        raise ValueError("Missing 'poem' field")

    # Enhance with metadata
    data['metadata'] = {
        'enhanced_at': datetime.now().isoformat(),
        'line_count': len(data['poem'].split('\n')),
        'word_count': len(data['poem'].split()),
        'char_count': len(data['poem'])
    }

    # Save enhanced draft
    with open(data_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"[ENHANCED] Draft enhanced with metadata ({data['metadata']['line_count']} lines)")

except Exception as e:
    print(f"[ERROR] Draft enhancement failed: {str(e)}")
    sys.exit(1)
