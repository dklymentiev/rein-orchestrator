# Refactor Plan: Tasks Separation

## Goal

Отделить динамические данные (tasks/outputs) от статических (flows/templates).

## Current State

```
agents/flows/deliberation/
├── deliberation.yaml        # template (static)
├── logic/run.py             # logic (static)
├── block_a.json             # OUTPUT (dynamic) ← WRONG!
├── block_b.json             # OUTPUT (dynamic) ← WRONG!
└── final.json               # OUTPUT (dynamic) ← WRONG!
```

## Target State

```
agents/flows/deliberation/
├── deliberation.yaml        # template (static)
└── logic/run.py             # logic (static)

tasks/task-20260101-001/
├── task.json                # metadata
├── status                   # running|completed|failed
├── dog.log                  # execution log
├── state.db                 # SQLite state
└── outputs/
    ├── block_a.json
    ├── block_b.json
    └── final.json
```

## Changes Required

### Phase 1: Task Directory Structure

**File:** `dog.py`

1. **Add task creation:**
```python
def create_task(self, flow_name: str, input_params: dict) -> str:
    task_id = f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    task_dir = os.path.join(self.tasks_root, task_id)

    os.makedirs(task_dir)
    os.makedirs(os.path.join(task_dir, "outputs"))

    task_json = {
        "id": task_id,
        "flow": flow_name,
        "input": input_params,
        "created": datetime.now().isoformat(),
        "status": "pending"
    }

    with open(os.path.join(task_dir, "task.json"), "w") as f:
        json.dump(task_json, f, indent=2)

    return task_id
```

2. **Change output path:**
```python
# BEFORE (line 655):
save_file = os.path.join(workflow_dir, save_filename)

# AFTER:
save_file = os.path.join(self.task_dir, "outputs", save_filename)
```

3. **Change log path:**
```python
# BEFORE:
self.run_dir = f"/tmp/dog-runs/run-{timestamp}"

# AFTER:
self.run_dir = self.task_dir  # logs go to task directory
```

4. **Add task_dir to context:**
```python
def __init__(self, workflow_file, task_id=None, input_params=None):
    self.tasks_root = os.path.join(os.path.dirname(__file__), "tasks")

    if task_id:
        self.task_dir = os.path.join(self.tasks_root, task_id)
    else:
        self.task_id = self.create_task(flow_name, input_params or {})
        self.task_dir = os.path.join(self.tasks_root, self.task_id)
```

### Phase 2: Logic Script Updates

**File:** `logic/run-specialist.py`

1. **Receive task context:**
```python
# BEFORE:
output_file = sys.stdin.read().strip()
workflow_dir = Path(output_file).parent

# AFTER:
input_json = sys.stdin.read().strip()
context = json.loads(input_json)
output_file = context["output_file"]
task_dir = context["task_dir"]
workflow_dir = context["workflow_dir"]  # still needed for reading YAML
```

2. **Substitute placeholders from task outputs:**
```python
# BEFORE:
filepath = workflow_dir / filename

# AFTER:
filepath = Path(task_dir) / "outputs" / filename
```

### Phase 3: Dog.py _run_logic Update

```python
def _run_logic(self, script_path: str, data_file: str, workflow_dir: str) -> bool:
    # Build context for logic script
    context = json.dumps({
        "output_file": data_file,
        "task_dir": self.task_dir,
        "task_id": self.task_id,
        "workflow_dir": workflow_dir,
        "task_input": self.task_input  # params from task.json
    })

    result = subprocess.run(
        ['python3', full_path],
        input=context,  # JSON instead of plain path
        ...
    )
```

### Phase 4: CLI Interface

```bash
# Current:
python3 dog.py agents/flows/deliberation/deliberation.yaml

# New:
python3 dog.py --flow deliberation --input '{"project": "X"}'
python3 dog.py --task task-20260101-001 --resume
python3 dog.py --task task-20260101-001 --status
```

### Phase 5: Clean Flow Directories

After refactor, remove old outputs from flow directories:
```bash
find agents/flows/ -name "*.json" -type f -delete
```

## File Changes Summary

| File | Changes |
|------|---------|
| `dog.py` | Task creation, output paths, context passing |
| `logic/run-specialist.py` | Parse JSON context, read from task outputs |
| `agents/flows/*/logic/*.py` | Same pattern as run-specialist.py |

## Migration

1. Create `tasks/` directory
2. Update dog.py
3. Update logic scripts
4. Test with new task
5. Clean old outputs from flow directories

## Testing

```bash
# Create task
python3 dog.py --flow deliberation --input '{"topic": "test"}'
# Output: Created task: task-20260101-001

# Check task
ls tasks/task-20260101-001/
# task.json  status  dog.log  state.db  outputs/

# Check outputs
ls tasks/task-20260101-001/outputs/
# block_a.json  block_b.json  final.json

# Check flow directory is clean
ls agents/flows/deliberation/
# deliberation.yaml  logic/  (NO json files)
```
