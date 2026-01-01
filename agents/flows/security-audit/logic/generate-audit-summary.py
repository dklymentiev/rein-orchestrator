#!/usr/bin/env python3
"""
Post-phase: Generate security audit summary and export formats
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

    # Validate audit report structure
    if 'security_rating' not in data:
        raise ValueError("Missing 'security_rating'")

    # Add audit metadata
    data['audit_metadata'] = {
        'completed_at': datetime.now().isoformat(),
        'audit_version': '2.0',
        'format': 'comprehensive_security_audit'
    }

    # Determine risk level color/category
    rating = data.get('security_rating', 0)
    if rating >= 8:
        risk_category = 'LOW'
    elif rating >= 6:
        risk_category = 'MEDIUM'
    elif rating >= 4:
        risk_category = 'HIGH'
    else:
        risk_category = 'CRITICAL'

    data['risk_category'] = risk_category

    # Add executive summary
    data['executive_summary'] = {
        'overall_rating': rating,
        'risk_level': data.get('risk_level', 'Unknown'),
        'risk_category': risk_category,
        'total_critical_issues': data.get('critical_issues', 0),
        'total_high_issues': data.get('high_issues', 0),
        'remediation_items': len(data.get('remediation_plan', [])),
        'estimated_effort_hours': data.get('estimated_effort', 'Unknown')
    }

    # Save final report
    with open(data_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"[REPORT] Audit report generated (Risk: {risk_category}, Rating: {rating}/10)")

except Exception as e:
    print(f"[ERROR] Audit summary generation failed: {str(e)}")
    sys.exit(1)
