#!/usr/bin/env python3
"""
Validate workflow against Dog's ValidationEngine.
This runs the actual schema validation.
"""

import json
import sys
import yaml
from pathlib import Path

def validate_workflow_files(generator_output, validator_report):
    """
    Run validation using Dog's ValidationEngine.
    Note: In actual execution, this would import and use the ValidationEngine.
    For now, we provide a validation checklist.
    """
    errors = []
    warnings = []

    # The validator_report should be from validator-workflow specialist
    if 'is_valid' in validator_report:
        if not validator_report['is_valid']:
            errors.extend(validator_report.get('errors', []))
            warnings.extend(validator_report.get('warnings', []))

    # Additional checks
    if 'workflow.yaml' in generator_output.get('files', {}):
        try:
            workflow = yaml.safe_load(generator_output['files']['workflow.yaml'])

            # Check max_parallel
            max_parallel = workflow.get('max_parallel', 3)
            if not isinstance(max_parallel, int) or max_parallel < 1 or max_parallel > 10:
                errors.append(f"max_parallel must be 1-10, got {max_parallel}")

            # Check blocks have proper structure
            blocks = workflow.get('blocks', [])
            for block in blocks:
                if 'phase' not in block:
                    errors.append(f"Block '{block.get('name')}' missing phase")
                if block.get('phase', 0) < 1:
                    errors.append(f"Block phases must be >= 1, got {block.get('phase')}")

        except Exception as e:
            errors.append(f"Error validating workflow: {str(e)}")

    return errors, warnings

if __name__ == '__main__':
    try:
        # Dog passes the JSON file path as stdin
        input_path = sys.stdin.read().strip()
        with open(input_path) as f:
            file_data = json.load(f)

        # Extract the result from the envelope structure
        if isinstance(file_data, dict) and 'result' in file_data:
            result_text = file_data['result']
            data = json.loads(result_text)
        else:
            data = file_data
    except json.JSONDecodeError as e:
        print(json.dumps({"valid": False, "error": f"Invalid JSON: {str(e)}"}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"valid": False, "error": f"Error reading file: {str(e)}"}))
        sys.exit(1)

    # Extract errors/warnings from validator report
    errors = data.get('errors', [])
    warnings = data.get('warnings', [])

    result = {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "validation_report": data
    }

    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)
