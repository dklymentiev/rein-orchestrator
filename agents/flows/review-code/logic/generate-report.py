#!/usr/bin/env python3
"""
Post-phase: Generate consolidated review report
"""
import json
import sys
from datetime import datetime

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

    # Add report metadata
    data['report'] = {
        'generated_at': datetime.now().isoformat(),
        'report_version': '1.0',
        'format': 'consolidated_review'
    }

    # Add approval status based on rating
    overall_rating = data.get('overall_rating', 0)
    data['approval'] = {
        'approved': overall_rating >= 7,
        'rating': overall_rating,
        'reasoning': 'Approved: Good quality' if overall_rating >= 7 else 'Needs improvement'
    }

    # Save report
    with open(data_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"[REPORT] Generated consolidated review (rating: {overall_rating}/10)")

except Exception as e:
    print(f"[ERROR] Report generation failed: {str(e)}")
    sys.exit(1)
