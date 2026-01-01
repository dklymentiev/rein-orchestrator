#!/usr/bin/env python3
"""
Post-phase: Validate and compare original vs revised poem
"""
import json
import sys

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

    # Validate revision structure
    if 'original' not in data or 'revised' not in data:
        raise ValueError("Missing 'original' or 'revised' field")

    # Calculate metrics
    original_len = len(data['original'])
    revised_len = len(data['revised'])
    size_change = revised_len - original_len

    # Add comparison metrics
    data['comparison'] = {
        'original_chars': original_len,
        'revised_chars': revised_len,
        'size_change': size_change,
        'size_change_pct': round(100 * size_change / original_len, 1) if original_len > 0 else 0,
        'was_modified': original_len != revised_len
    }

    # Save with metrics
    with open(data_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"[VALID] Revision validated (size change: {size_change:+d} chars)")

except Exception as e:
    print(f"[ERROR] Revision validation failed: {str(e)}")
    sys.exit(1)
