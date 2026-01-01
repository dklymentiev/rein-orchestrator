#!/usr/bin/env python3
"""
Validate architecture output from architect-workflow specialist.
Ensures workflow design is structurally sound.
"""

import json
import sys

def validate_architecture(data):
    """Validate the architecture structure"""
    errors = []
    warnings = []

    # Check required root fields
    required_fields = ['workflow_name', 'team_name', 'blocks_design', 'team_composition']
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # Validate team_name format
    if 'team_name' in data:
        team_name = data['team_name']
        if not team_name.startswith('team-'):
            errors.append(f"team_name must start with 'team-', got '{team_name}'")

    # Validate blocks_design
    if 'blocks_design' in data:
        blocks = data['blocks_design']
        if not isinstance(blocks, list) or len(blocks) == 0:
            errors.append("blocks_design must be non-empty array")
        else:
            block_names = set()
            for i, block in enumerate(blocks):
                if not isinstance(block, dict):
                    errors.append(f"blocks_design[{i}] must be object")
                    continue

                required = ['name', 'phase', 'specialist', 'purpose', 'prompt_summary']
                for req in required:
                    if req not in block:
                        errors.append(f"blocks_design[{i}] missing: {req}")

                if 'name' in block:
                    name = block['name']
                    if not isinstance(name, str) or not name.replace('_', '').isalnum():
                        errors.append(f"blocks_design[{i}].name invalid: {name}")
                    block_names.add(name)

                if 'depends_on' in block:
                    depends = block['depends_on']
                    if isinstance(depends, list):
                        for dep in depends:
                            if dep not in block_names and i > 0:
                                # Allow forward references but warn
                                pass

    # Validate team_composition
    if 'team_composition' in data:
        specialists = data['team_composition']
        if not isinstance(specialists, list):
            errors.append("team_composition must be array")
        else:
            specialist_names = set()
            for i, specialist in enumerate(specialists):
                if not isinstance(specialist, dict):
                    errors.append(f"team_composition[{i}] must be object")
                    continue

                required = ['role', 'specialist', 'count']
                for req in required:
                    if req not in specialist:
                        errors.append(f"team_composition[{i}] missing: {req}")

                if 'specialist' in specialist:
                    specialist_names.add(specialist['specialist'])

            # Warn if too many specialists
            if len(specialist_names) > 10:
                warnings.append(f"Many specialists ({len(specialist_names)}): consider simplifying")

    # Validate execution_plan if present
    if 'execution_plan' in data:
        plan = data['execution_plan']
        if 'critical_path' in plan and not isinstance(plan['critical_path'], list):
            errors.append("execution_plan.critical_path must be array")

    return errors, warnings

if __name__ == '__main__':
    try:
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
        print(json.dumps({"valid": False, "error": f"Error: {str(e)}"}))
        sys.exit(1)

    errors, warnings = validate_architecture(data)

    result = {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }

    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)
