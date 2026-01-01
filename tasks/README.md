# Tasks - Execution Instances of Flows

This directory contains task instances that use flow templates from `../agents/flows/`.

## Structure

Each task is a self-contained directory with:

- `task.yaml` - Configuration (which flow to use, parameters)
- `status.json` - Execution state (pending/running/completed/failed)
- `inputs/` - Input data for the task
- `outputs/` - Results after execution

## Quick Start

```bash
# Create a new task
mkdir -p task-20260101-my-task/{inputs,outputs}

# Create task.yaml (specify which flow to run)
cat > task-20260101-my-task/task.yaml << 'EOF'
id: task-20260101-my-task
flow: create-poem              # Use this flow template
output_dir: ./outputs
EOF

# Create status.json
cat > task-20260101-my-task/status.json << 'EOF'
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

# Run the task
python3 ../dog.py --task task-20260101-my-task

# Check results
cat task-20260101-my-task/outputs/*.json
cat task-20260101-my-task/status.json
```

## Available Flows

- `create-poem` - Generate, critique, and refine poetry
- `review-code` - Analyze code architecture and quality
- `security-audit` - Scan for vulnerabilities and threats

See `../agents/flows/README.md` for flow details.

## Task State Transitions

```
pending → running → completed
                ↘ failed
```

The `status.json` file tracks this automatically.

## Results Location

Results are always in `<task-dir>/outputs/`:

- `ideation.json` - Initial ideas/themes
- `draft.json` - First version
- `critique.json` - Feedback
- `final.json` - Revised version (for poetry tasks)
- `final_critique.json` - Final assessment
- `.yaml`, `.env` - Configuration files (copied from flow)

## Integration

### Memory Callback

Save results to memory system:

```yaml
# In task.yaml
callback:
  save_to_memory: true
  memory_config:
    guid: afc9f8a3              # Project GUID
    tags:
      - type:artifact
      - stage:completed
      - project:poetry
      - date:2026-01-01
```

### Monitoring

Check task progress:

```bash
cat tasks/task-20260101-001/status.json | jq .

# Or watch it
watch cat tasks/task-20260101-001/status.json
```

## Cleanup

Remove old tasks:

```bash
# Archive to backup
tar czf task-20260101-001.tar.gz task-20260101-001/
mv task-20260101-001.tar.gz /backups/

# Remove directory
rm -rf task-20260101-001/
```
