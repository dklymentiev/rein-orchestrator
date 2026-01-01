#!/usr/bin/env python3
"""
Validate analysis output from analyzer-requirements specialist.
Ensures the analysis JSON is well-formed and has required fields.
"""

import json
import sys
from pathlib import Path

def validate_analysis(data):
    """Validate the analysis structure"""
    errors = []
    warnings = []

    # Check required root fields
    required_fields = [
        'workflow_name', 'workflow_title', 'description',
        'analysis', 'stages', 'specialists_needed'
    ]
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # Validate workflow_name format
    if 'workflow_name' in data:
        name = data['workflow_name']
        if not isinstance(name, str) or not name:
            errors.append("workflow_name must be non-empty string")
        elif not name.replace('-', '').replace('_', '').isalnum() or name[0].isdigit():
            errors.append(f"workflow_name '{name}' must match [a-z0-9-_]+ pattern")

    # Validate analysis object
    if 'analysis' in data:
        analysis = data['analysis']
        if not isinstance(analysis, dict):
            errors.append("analysis must be an object")
        else:
            if 'complexity' in analysis and analysis['complexity'] not in ['simple', 'moderate', 'complex']:
                errors.append(f"analysis.complexity must be one of: simple, moderate, complex")
            if 'estimated_blocks' in analysis and not isinstance(analysis['estimated_blocks'], int):
                errors.append("analysis.estimated_blocks must be integer")

    # Validate stages
    if 'stages' in data:
        stages = data['stages']
        if not isinstance(stages, list):
            errors.append("stages must be an array")
        elif len(stages) == 0:
            errors.append("stages array cannot be empty")
        else:
            for i, stage in enumerate(stages):
                if not isinstance(stage, dict):
                    errors.append(f"stages[{i}] must be an object")
                else:
                    required = ['phase', 'name', 'purpose', 'specialist_role']
                    for req_field in required:
                        if req_field not in stage:
                            errors.append(f"stages[{i}] missing required field: {req_field}")

    # Validate specialists_needed
    if 'specialists_needed' in data:
        specialists = data['specialists_needed']
        if not isinstance(specialists, list):
            errors.append("specialists_needed must be an array")
        else:
            for i, specialist in enumerate(specialists):
                if not isinstance(specialist, dict):
                    errors.append(f"specialists_needed[{i}] must be an object")
                else:
                    required = ['role', 'description', 'count']
                    for req_field in required:
                        if req_field not in specialist:
                            errors.append(f"specialists_needed[{i}] missing: {req_field}")

    return errors, warnings

if __name__ == '__main__':
    # Read input from file (path provided as argument or via stdin)
    try:
        # Dog passes the JSON file path as stdin
        input_path = sys.stdin.read().strip()
        with open(input_path) as f:
            file_data = json.load(f)

        # Extract the result from the envelope structure
        if isinstance(file_data, dict) and 'result' in file_data:
            result_text = file_data['result']
            # The result is JSON as string, parse it
            data = json.loads(result_text)
        else:
            data = file_data
    except json.JSONDecodeError as e:
        print(json.dumps({
            "valid": False,
            "error": f"Invalid JSON: {str(e)}"
        }))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({
            "valid": False,
            "error": f"Error reading file: {str(e)}"
        }))
        sys.exit(1)

    errors, warnings = validate_analysis(data)

    result = {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "analysis_data": data if len(errors) == 0 else None
    }

    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)
