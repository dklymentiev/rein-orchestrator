#!/usr/bin/env python3
"""
Validate-phase: Validate vulnerability scan results
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

    # Validate structure
    if 'vulnerabilities' not in data:
        raise ValueError("Missing 'vulnerabilities' field")

    if not isinstance(data['vulnerabilities'], list):
        raise ValueError("'vulnerabilities' must be a list")

    # Count by severity
    critical_count = 0
    high_count = 0
    medium_count = 0
    low_count = 0

    severity_map = {
        'Critical': 'critical_count',
        'High': 'high_count',
        'Medium': 'medium_count',
        'Low': 'low_count'
    }

    for vuln in data['vulnerabilities']:
        if 'severity' not in vuln:
            raise ValueError("Vulnerability missing 'severity'")
        if 'issue' not in vuln:
            raise ValueError("Vulnerability missing 'issue'")

        severity = vuln['severity']
        if severity == 'Critical':
            critical_count += 1
        elif severity == 'High':
            high_count += 1
        elif severity == 'Medium':
            medium_count += 1
        elif severity == 'Low':
            low_count += 1

    # Validate counts match
    reported_critical = data.get('critical_count', 0)
    reported_high = data.get('high_count', 0)

    if reported_critical != critical_count:
        print(f"[WARN] Critical count mismatch: reported {reported_critical}, found {critical_count}")

    print(f"[VALID] Vulnerability scan validated (C:{critical_count} H:{high_count} M:{medium_count} L:{low_count})")

except Exception as e:
    print(f"[ERROR] Vulnerability validation failed: {str(e)}")
    sys.exit(1)
