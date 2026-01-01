#!/usr/bin/env python3
"""
Post-phase: Enhance threat analysis with risk scoring
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
    if 'threats' not in data:
        raise ValueError("Missing 'threats' field")

    # Calculate risk scores (severity × likelihood)
    severity_map = {'Critical': 5, 'High': 4, 'Medium': 3, 'Low': 2}
    likelihood_map = {'High': 3, 'Medium': 2, 'Low': 1}

    for threat in data.get('threats', []):
        sev = severity_map.get(threat.get('severity', 'Medium'), 3)
        like = likelihood_map.get(threat.get('likelihood', 'Low'), 1)
        threat['risk_score'] = sev * like

    # Add risk summary
    risk_scores = [t.get('risk_score', 0) for t in data.get('threats', [])]
    data['risk_summary'] = {
        'total_threats': len(data.get('threats', [])),
        'avg_risk_score': sum(risk_scores) / len(risk_scores) if risk_scores else 0,
        'max_risk_score': max(risk_scores) if risk_scores else 0
    }

    with open(data_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"[ENHANCED] Threat analysis enhanced ({len(data.get('threats', []))} threats analyzed)")

except Exception as e:
    print(f"[ERROR] Threat enhancement failed: {str(e)}")
    sys.exit(1)
