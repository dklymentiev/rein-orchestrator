# Tasks System - Dog v2.5+

Task-driven architecture for dog.py. Separates flow templates from task executions with clean input/output organization.

## Architecture

```
dog.py (Orchestrator)
  ↓
  ├─ flows/        (Templates - reusable)
  │  ├─ create-poem/
  │  │  ├─ create-poem.yaml
  │  │  ├─ .env
  │  │  ├─ logic/
  │  │  └─ README.md
  │  ├─ review-code/
  │  └─ security-audit/
  │
  └─ tasks/        (Executions - with results)
     ├─ task-20260101-001/
     │  ├─ task.yaml        (Describes what to do)
     │  ├─ status.json      (Tracks execution state)
     │  ├─ inputs/          (Input data for the task)
     │  └─ outputs/         (Results from execution)
     │
     └─ task-20260101-002/
        └─ ...
```

## Usage

### Create a Task

```bash
# Create task directory
mkdir -p /server/scripts/agent-pm2-dog/tasks/task-20260101-my-task/{inputs,outputs}

# Create task.yaml
cat > /server/scripts/agent-pm2-dog/tasks/task-20260101-my-task/task.yaml << 'EOF'
id: task-20260101-my-task
name: "My Poetry Task"
description: "Create and refine a poem"

# Which flow to use
flow: create-poem

# Task parameters (override defaults)
params:
  team: team-poetry
  max_parallel: 3

# Where to save results
output_dir: ./outputs

# Optional: save result to memory after completion
callback:
  save_to_memory: true
  memory_config:
    guid: afc9f8a3
    tags:
      - type:artifact
      - project:poetry
      - date:2026-01-01
EOF

# Create status.json
cat > /server/scripts/agent-pm2-dog/tasks/task-20260101-my-task/status.json << 'EOF'
{
  "task_id": "task-20260101-my-task",
  "status": "pending",
  "created_at": "2026-01-01T00:00:00Z",
  "started_at": null,
  "completed_at": null,
  "progress": 0,
  "blocks_completed": 0,
  "blocks_total": 0,
  "error": null,
  "output_dir": "./outputs"
}
EOF
```

### Run a Task

```bash
# Run the task
python3 dog.py --task /server/scripts/agent-pm2-dog/tasks/task-20260101-my-task

# Or relative path
cd /server/scripts/agent-pm2-dog
python3 dog.py --task tasks/task-20260101-my-task
```

## File Structure

### task.yaml

```yaml
# Unique task identifier
id: task-20260101-001

# Human-readable name
name: "Create poetry - test task"
description: "Generate, critique, and refine a poem using flow-based specialists"

# Which flow template to use
flow: create-poem

# Parameters to override defaults
params:
  team: team-poetry
  max_parallel: 3

# Where to save results (relative to task dir or absolute)
output_dir: ./outputs

# Task metadata
created_at: "2026-01-01T00:45:00Z"
created_by: claude-code

# Optional: callback after completion
callback:
  save_to_memory: true
  memory_config:
    guid: afc9f8a3        # Project GUID
    tags:
      - type:artifact     # What was created
      - stage:completed   # Current stage
      - project:poetry    # Project name
      - date:2026-01-01
```

### status.json

Automatically created and updated. Tracks task execution state:

```json
{
  "task_id": "task-20260101-001",
  "status": "completed",        // pending, running, completed, failed
  "created_at": "2026-01-01T00:49:30Z",
  "started_at": "2026-01-01T00:49:30Z",
  "completed_at": "2026-01-01T00:50:21Z",
  "progress": 100,              // 0-100%
  "blocks_completed": 5,        // How many blocks done
  "blocks_total": 5,            // Total blocks
  "error": null,                // Error message if failed
  "output_dir": "./outputs"
}
```

**Status values:**
- `pending` - Task created, not started
- `running` - Task is executing
- `completed` - All blocks completed successfully
- `failed` - One or more blocks failed

## Data Flow

```
1. Create task directory structure
   └─ task.yaml (specifies which flow to use)
   └─ status.json (tracks execution)

2. Run: python3 dog.py --task <task-dir>
   └─ dog.py reads task.yaml
   └─ Finds flow: agents/flows/create-poem/
   └─ Executes blocks (same as normal flow mode)
   └─ Saves results to: task/<task-id>/outputs/

3. Completion
   └─ status.json updated with results
   └─ Results copied to outputs/ directory
   └─ Optional: saved to memory with callback

4. Access results
   └─ cat tasks/task-20260101-001/outputs/*.json
   └─ Or retrieve from memory if saved there
```

## Examples

### Create Poetry Task

```bash
# Create task
mkdir -p /server/scripts/agent-pm2-dog/tasks/poem-001/{inputs,outputs}

cat > /server/scripts/agent-pm2-dog/tasks/poem-001/task.yaml << 'EOF'
id: poem-001
flow: create-poem
output_dir: ./outputs
EOF

# Run it
python3 dog.py --task tasks/poem-001

# Check results
ls tasks/poem-001/outputs/
cat tasks/poem-001/outputs/final.json
cat tasks/poem-001/status.json
```

### Create Task from Maestro

```bash
# Maestro or another orchestrator creates task
mkdir -p /server/scripts/agent-pm2-dog/tasks/maestro-task-$(date +%s)/{inputs,outputs}

cat > /server/scripts/agent-pm2-dog/tasks/maestro-task-*/task.yaml << 'EOF'
id: maestro-task-001
flow: create-poem
created_by: maestro
callback:
  save_to_memory: true
  memory_config:
    guid: afc9f8a3
    tags:
      - type:artifact
      - source:maestro
EOF

# Then run via dog.py
python3 dog.py --task /server/scripts/agent-pm2-dog/tasks/maestro-task-*/
```

## Comparison: Flow Mode vs Task Mode

| Aspect | Flow Mode | Task Mode |
|--------|-----------|-----------|
| Usage | `dog.py flow.yaml` | `dog.py --task task-dir` |
| Results | `/tmp/dog-runs/run-ID/` | `task-dir/outputs/` |
| Status tracking | Console/DB only | `status.json` |
| Reusability | Single run | Task template |
| Integration | Manual | Via callbacks |
| Clean separation | No | Yes (templates vs executions) |

## Benefits of Tasks

1. **Clean separation** - Flows are templates, tasks are executions
2. **Status tracking** - `status.json` shows exactly where execution is
3. **Results location** - Always in `task-dir/outputs/` (predictable)
4. **Integration ready** - Callbacks can save to memory, webhooks, etc.
5. **Reproducibility** - Save task.yaml, re-run later with `--task`
6. **Scalability** - Multiple tasks can reference same flow
7. **Monitoring** - Check `status.json` to see progress from any script

## Notes

- Flows stay in `agents/flows/` - templates only
- Tasks created in `agents/tasks/` - with full lifecycle
- Each task is independent (can run in parallel)
- Results are copied to `outputs/` after completion
- Status file updated at key points: created, running, completed/failed
- Optional memory integration for archiving results
