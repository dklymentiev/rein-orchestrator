# Flows - Specialist Workflow Orchestration

**Architecture:** Flow-Centric Model
**Status:** Phase 2.5 Complete - Logic Phases Supported

## Overview

Flows are self-contained workflow directories combining:
1. **Workflow YAML** - Process definition with blocks and dependencies
2. **Logic Scripts** - Python and Shell scripts for data processing
3. **Documentation** - Flow-specific README with architecture details

## Directory Structure

```
flows/
├── create-poem/                    (Example: Poetry creation flow)
│   ├── create-poem.yaml           (Workflow definition)
│   ├── logic/                     (Data processing scripts)
│   │   ├── validate-themes.py     (validate phase - check themes)
│   │   ├── enhance-draft.py       (post phase - add metadata)
│   │   └── validate-revision.py   (post phase - compare versions)
│   └── README.md                  (Flow documentation)
│
├── review-code/                   (Example: Code review flow)
│   ├── review-code.yaml          (Workflow definition)
│   ├── logic/                    (Data processing scripts)
│   │   ├── format-architecture.py (post phase)
│   │   ├── validate-code-quality.sh (validate phase)
│   │   └── generate-report.py    (post phase)
│   └── README.md
│
└── security-audit/               (Example: Security audit flow)
    ├── security-audit.yaml       (Workflow definition)
    ├── logic/                    (Data processing scripts)
    │   ├── enhance-threats.py    (post phase)
    │   ├── validate-vulnerabilities.py (validate phase)
    │   └── generate-audit-summary.py (post phase)
    └── README.md
```

## How It Works

### Execution Flow

```
dog.py agents/flows/create-poem/create-poem.yaml
       ↓
Load workflow YAML
       ↓
For each block:
  1. PRE-PHASE: Run logic/pre-script.py (if exists)
  2. CLAUDE-PHASE: Call Claude API with specialists
  3. POST-PHASE: Run logic/post-script.py (if exists)
  4. VALIDATE-PHASE: Run logic/validate-script.py (if exists)
       ↓
Save results (JSON files)
```

### Logic Phases

YAML supports four logic phases per block:

```yaml
blocks:
  - stage: my-block
    agents: [specialist-1, specialist-2]
    prompt: "Task description..."
    logic:
      pre: logic/prepare-data.py          # Before Claude
      post: logic/enhance-results.py      # After Claude
      validate: logic/check-quality.py    # Validation
      custom: logic/transform-only.sh     # Skip Claude entirely
    save_as: output.json
```

## Creating a New Flow

### 1. Create Flow Directory

```bash
mkdir -p agents/flows/my-flow/logic
cd agents/flows/my-flow
```

### 2. Write Workflow YAML

```yaml
# my-flow.yaml
name: my-flow
team: team-name
description: Flow description

blocks:
  - stage: step-1
    agents: [specialist-1]
    prompt: "Task..."
    logic:
      validate: logic/validate-step1.py
    save_as: step-1.json

  - stage: step-2
    agents: [specialist-2]
    prompt: "Based on: {{ step-1.json }}"
    depends_on: [step-1]
    logic:
      post: logic/enhance-step2.py
    save_as: step-2.json
```

### 3. Write Logic Scripts

```python
# logic/validate-step1.py
#!/usr/bin/env python3
import json
import sys

data_file = sys.argv[1]

with open(data_file) as f:
    data = json.load(f)

# Validate data structure
if 'required_field' not in data:
    print("[ERROR] Missing required_field")
    sys.exit(1)

print("[VALID] Data validated")
```

### 4. Write README.md

Document your flow with:
- Description
- Blocks and their purposes
- Logic scripts and phases
- Data flow diagram
- Example usage

### 5. Run Flow

```bash
cd /server/scripts/agent-pm2-dog
python3 dog.py agents/flows/my-flow/my-flow.yaml
```

## Logic Script Guidelines

### Python Scripts

```python
#!/usr/bin/env python3
import json
import sys

# Receive data file as first argument
data_file = sys.argv[1]

# Load JSON data
with open(data_file) as f:
    data = json.load(f)

# Process...

# For validation failures: exit(1)
# For success: modify data and save back
with open(data_file, 'w') as f:
    json.dump(data, f)

# Log status (will be captured)
print("[STATUS] What was done")
```

### Shell Scripts

```bash
#!/bin/bash
# Receive data file as first argument
DATA_FILE=$1

# Check file exists
[ -f "$DATA_FILE" ] || { echo "[ERROR] File not found"; exit 1; }

# Use jq for JSON processing
jq '.field | length' "$DATA_FILE"

# Log status
echo "[VALID] Validation passed"
```

## Data Flow Between Blocks

Blocks can reference previous results:

```yaml
blocks:
  - stage: step-1
    save_as: step-1.json    # Creates step-1.json

  - stage: step-2
    prompt: "Input: {{ step-1.json }}"    # Automatic substitution
    depends_on: [step-1]
    save_as: step-2.json

  - stage: step-3
    prompt: |
      Original: {{ step-1.json }}
      Processed: {{ step-2.json }}
    depends_on: [step-2]
    save_as: step-3.json
```

Results are loaded and substituted automatically by dog.py.

## Parallelism

Blocks can run in parallel if they don't depend on each other:

```yaml
blocks:
  - stage: analysis-1
    parallel: true
    save_as: analysis-1.json

  - stage: analysis-2
    parallel: true
    save_as: analysis-2.json
    # Runs simultaneously with analysis-1

  - stage: synthesis
    depends_on: [analysis-1, analysis-2]    # Waits for both
    save_as: result.json
```

## Example Flows

### Poetry Creation (create-poem)
- Specialists: poet-specialist, critic-specialist
- Logic: validate themes, enhance draft, compare versions
- Purpose: Create poetry with iterative feedback

### Code Review (review-code)
- Specialists: developer, architect, tester
- Logic: format reviews, validate quality, generate report
- Purpose: Comprehensive code review from multiple perspectives

### Security Audit (security-audit)
- Specialists: security-expert, architect, debugger, analyst
- Logic: enhance threats, validate vulnerabilities, generate summary
- Purpose: Thorough security assessment with integrated report

## Best Practices

1. **One Flow = One Process**
   - Keep flows focused and cohesive
   - Don't mix unrelated tasks

2. **Meaningful Names**
   - Flow names should clearly describe purpose
   - Block stages should be sequential nouns (ideation, draft, critique, revision)

3. **Logic Scripts**
   - Keep scripts simple and focused
   - Use proper error handling (exit codes)
   - Add logging/print statements for visibility

4. **Documentation**
   - Every flow should have README.md
   - Document data structures in blocks
   - Provide example usage

5. **Dependencies**
   - Mark all real dependencies
   - Use parallel: true for independent blocks
   - Structure for efficiency

## Running Flows

```bash
cd /server/scripts/agent-pm2-dog

# Run a flow
python3 dog.py agents/flows/create-poem/create-poem.yaml

# Check logs
tail -f /tmp/dog-runs/run-*/dog.log

# View results
cat /tmp/dog-runs/run-*/step-1.json | jq .
```

## Troubleshooting

### Logic Script Fails
- Check script is executable: `chmod +x logic/script.py`
- Check exit code: scripts must exit(0) on success
- Check logs: look in dog.log for error details

### Data Not Substituted
- Ensure {{ file.json }} path exists
- Check file was created by previous block
- Verify path in block's save_as matches reference

### Block Dependency Issues
- Verify depends_on lists exactly match stage names
- Check for circular dependencies
- Ensure all dependencies complete before running

## Future Enhancements

1. Flow templates and inheritance
2. Conditional execution (if/else)
3. Loop blocks for batch processing
4. Custom metrics and monitoring
5. Flow versioning and rollback
6. Integration with version control
7. Scheduled flow execution
8. Flow composition (flows calling flows)
