#!/usr/bin/env python3
"""
Save generated workflow files to disk.
This is the custom logic phase that actually writes the files.
"""

import json
import sys
import os
from pathlib import Path
import yaml

def save_workflow_files(generation_data, validation_data):
    """Save workflow files to appropriate directories"""
    result = {
        "status": "failed",
        "errors": [],
        "files_created": [],
        "files_location": {}
    }

    # Check if validation passed
    if validation_data and not validation_data.get('is_valid'):
        result["errors"] = validation_data.get('errors', ['Validation failed'])
        return result

    try:
        # Extract data
        workflow_name = generation_data.get('workflow_name')
        if not workflow_name:
            result["errors"].append("workflow_name not found in generation data")
            return result

        files = generation_data.get('files', {})
        workflow_yaml = files.get('workflow.yaml')
        team_yaml = files.get('team.yaml')

        if not workflow_yaml or not team_yaml:
            result["errors"].append("Missing workflow.yaml or team.yaml")
            return result

        # Create directories
        agents_dir = Path(__file__).parent.parent.parent
        flows_dir = agents_dir / 'flows' / workflow_name
        teams_dir = agents_dir / 'teams'
        specialists_dir = agents_dir / 'specialists'

        flows_dir.mkdir(parents=True, exist_ok=True)
        teams_dir.mkdir(parents=True, exist_ok=True)
        specialists_dir.mkdir(parents=True, exist_ok=True)

        # Save workflow.yaml
        workflow_path = flows_dir / 'workflow-generation.yaml'
        # Rename to workflow_name.yaml
        workflow_path = flows_dir / f'{workflow_name}.yaml'

        with open(workflow_path, 'w') as f:
            f.write(workflow_yaml)
        result["files_created"].append(f'{workflow_name}.yaml')
        result["files_location"]["workflow"] = str(workflow_path)

        # Save team.yaml
        team_yaml_data = yaml.safe_load(team_yaml)
        team_name = team_yaml_data.get('name', f'team-{workflow_name}')
        team_path = teams_dir / f'{team_name}.yaml'

        with open(team_path, 'w') as f:
            f.write(team_yaml)
        result["files_created"].append(f'{team_name}.yaml')
        result["files_location"]["team"] = str(team_path)

        # Create specialist stub files
        specialists_to_create = generation_data.get('specialists_to_create', [])
        for specialist_spec in specialists_to_create:
            filename = specialist_spec.get('filename')
            role = specialist_spec.get('role', 'New specialist')

            if filename:
                specialist_path = specialists_dir / filename
                # Create stub if doesn't exist
                if not specialist_path.exists():
                    stub_content = f"""# {role}

## Role
{role}

## Your Task

[Task description here - this is a stub file that should be customized]

## Output Format

[Expected output format]
"""
                    with open(specialist_path, 'w') as f:
                        f.write(stub_content)
                    result["files_created"].append(filename)

        result["status"] = "saved"
        result["workflow_name"] = workflow_name

    except Exception as e:
        result["errors"].append(f"Error saving files: {str(e)}")
        result["status"] = "failed"

    return result

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
        print(json.dumps({
            "status": "failed",
            "errors": [f"Invalid JSON input: {str(e)}"],
            "files_created": []
        }))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({
            "status": "failed",
            "errors": [f"Error reading file: {str(e)}"],
            "files_created": []
        }))
        sys.exit(1)

    # The data should contain both generation and validation results
    generation_data = data.get('generation_data') or data
    validation_data = data.get('validation_data')

    result = save_workflow_files(generation_data, validation_data)

    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "saved" else 1)
