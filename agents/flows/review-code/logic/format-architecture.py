#!/usr/bin/env python3
"""
Post-phase: Format and enhance architecture review
"""
import json
import sys

def extract_json_from_text(text):
    """Extract JSON object from text that may contain prose around it"""
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
        data = extract_json_from_text(result_str)
        if not data:
            data = envelope

    # Validate required fields
    if 'design_assessment' not in data:
        raise ValueError("Missing 'design_assessment'")

    # Enhance with processing info
    data['processed'] = True
    data['review_type'] = 'architecture'

    # Count recommendations
    if 'recommendations' in data and isinstance(data['recommendations'], list):
        data['recommendation_count'] = len(data['recommendations'])

    with open(data_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("[FORMATTED] Architecture review formatted and enhanced")

except Exception as e:
    print(f"[ERROR] Architecture formatting failed: {str(e)}")
    sys.exit(1)
