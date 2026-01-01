#!/usr/bin/env python3
"""
Validate YAML structure output from generator-yaml specialist.
Ensures generated YAML is valid before running through Dog's validator.
"""

import json
import sys
import yaml

def validate_yaml_content(yaml_content, file_type):
    """Validate YAML syntax and structure"""
    errors = []
    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        return [f"{file_type} YAML syntax error: {str(e)}"]

    if not isinstance(data, dict):
        return [f"{file_type} must be a YAML object"]

    # Check schema_version
    if data.get('schema_version') != '2.5.3':
        errors.append(f"{file_type} schema_version must be '2.5.3', got '{data.get('schema_version')}'")

    return errors

def validate_yaml_files(generator_output):
    """Validate the generator output JSON"""
    errors = []
    warnings = []

    if 'files' not in generator_output:
        errors.append("Missing 'files' field in generator output")
        return errors, warnings

    files = generator_output['files']

    # Check workflow.yaml
    if 'workflow.yaml' in files:
        yaml_errors = validate_yaml_content(files['workflow.yaml'], 'workflow.yaml')
        errors.extend(yaml_errors)

        # Try to parse and validate structure
        try:
            workflow = yaml.safe_load(files['workflow.yaml'])
            if 'name' not in workflow:
                errors.append("workflow.yaml missing 'name'")
            if 'team' not in workflow:
                errors.append("workflow.yaml missing 'team'")
            if 'blocks' not in workflow or not isinstance(workflow['blocks'], list):
                errors.append("workflow.yaml 'blocks' must be non-empty array")
            else:
                block_names = {b.get('name') for b in workflow['blocks'] if isinstance(b, dict)}
                for i, block in enumerate(workflow['blocks']):
                    if isinstance(block, dict):
                        if 'name' not in block or 'specialist' not in block:
                            errors.append(f"workflow block {i} missing name or specialist")
                        # Check depends_on references
                        for dep in block.get('depends_on', []):
                            if dep not in block_names:
                                errors.append(f"Block '{block.get('name')}' depends on undefined block '{dep}'")
        except Exception as e:
            errors.append(f"Error parsing workflow.yaml: {str(e)}")

    # Check team.yaml
    if 'team.yaml' in files:
        yaml_errors = validate_yaml_content(files['team.yaml'], 'team.yaml')
        errors.extend(yaml_errors)

        try:
            team = yaml.safe_load(files['team.yaml'])
            if 'name' not in team:
                errors.append("team.yaml missing 'name'")
            if 'specialists' not in team:
                errors.append("team.yaml missing 'specialists'")
        except Exception as e:
            errors.append(f"Error parsing team.yaml: {str(e)}")

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

    errors, warnings = validate_yaml_files(data)

    result = {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }

    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)
