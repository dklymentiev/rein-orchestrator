# Dog Architecture

## Overview

Dog - системный процесс (daemon), который получает задачи и выполняет их используя flows как шаблоны.

```
                              DOG (daemon)
                                   │
            ┌──────────────────────┼──────────────────────┐
            │                      │                      │
            ▼                      ▼                      ▼
      ┌──────────┐          ┌──────────┐          ┌──────────┐
      │ TASK-001 │          │ TASK-002 │          │ TASK-003 │
      │ outputs/ │          │ outputs/ │          │ outputs/ │
      └──────────┘          └──────────┘          └──────────┘
            │                      │                      │
            │ uses (read-only)     │                      │
            ▼                      ▼                      ▼
      ┌─────────────────────────────────────────────────────────┐
      │                    FLOWS (templates)                    │
      │                    TEAMS (definitions)                  │
      │                    SPECIALISTS (prompts)                │
      └─────────────────────────────────────────────────────────┘
```

## Static Entities (Templates - Read Only)

### Specialists
`agents/specialists/*.md`

Agnostic system prompts.

```markdown
# Prompt Engineer Specialist

You are an expert in prompt engineering...
```

### Teams
`agents/teams/team-*.yaml`

Team prompt + references to specialists.

```yaml
name: team-deliberation
specialists:
  - prompt-engineer-specialist
  - workflow-architect
  - quality-assurance-specialist
collaboration_tone: analytical
```

### Flows
`agents/flows/<name>/<name>.yaml`

Reusable workflow templates. NO outputs here.

```yaml
schema_version: "2.5.3"
name: deliberation
team: team-deliberation

blocks:
  - name: initial_analysis
    specialist: prompt-engineer
    prompt: "Analyze {{ task.input.project }}..."
    depends_on: []
    logic:
      pre: logic/run-specialist.py
      custom: true
```

### Logic Scripts
`agents/flows/<name>/logic/*.py`

Execution logic. Receives task context, produces output.

## Dynamic Entities (Runtime)

### Dog Daemon
`/server/scripts/agent-pm2-dog/dog.py`

System process that:
- Receives tasks
- Creates task directories
- Executes flows
- Manages state

### Tasks
`tasks/<task-id>/`

Runtime instances. All outputs go here.

```
tasks/
├── task-20260101-001/
│   ├── task.json                 # Task metadata
│   ├── status                    # running|completed|failed
│   ├── dog.log                   # Execution log
│   ├── state.db                  # SQLite state
│   └── outputs/
│       ├── initial_analysis.json
│       ├── cross_review.json
│       └── final_recommendation.json
│
├── task-20260101-002/
│   └── ...
```

**task.json:**
```json
{
  "id": "task-20260101-001",
  "flow": "deliberation",
  "input": {
    "project": "dog-vs-conductor",
    "question": "Which orchestrator to use?"
  },
  "created": "2026-01-01T14:00:00Z",
  "status": "completed"
}
```

## Data Flow

```
1. Task Created
   dog.py receives: "deliberation team investigate dog-vs-conductor"
        │
        ▼
2. Task Directory Created
   tasks/task-20260101-001/
   tasks/task-20260101-001/task.json
   tasks/task-20260101-001/outputs/
        │
        ▼
3. Flow Loaded (read-only)
   agents/flows/deliberation/deliberation.yaml
        │
        ▼
4. Blocks Executed
   For each block:
     - Load specialist prompt (read-only)
     - Run logic script
     - Save to tasks/task-xxx/outputs/block_name.json
        │
        ▼
5. Dependencies Resolved
   {{ initial_analysis.json }} → reads from outputs/
        │
        ▼
6. Task Completed
   tasks/task-20260101-001/status = completed
```

## Key Principles

### 1. Flows are Templates
- Read-only
- Reusable across many tasks
- Never contain outputs

### 2. Tasks are Instances
- Created per execution
- Contain all outputs
- Isolated from each other

### 3. Clean Separation

| Directory | Content | Access |
|-----------|---------|--------|
| `agents/specialists/` | System prompts | Read-only |
| `agents/teams/` | Team definitions | Read-only |
| `agents/flows/` | Workflow templates + logic | Read-only |
| `tasks/<id>/` | Outputs, logs, state | Read-write |

### 4. Dog as Daemon

```
┌─────────────────────────────────────────┐
│              DOG DAEMON                 │
│                                         │
│  - Listens for tasks (API/CLI/Queue)   │
│  - Creates task directories            │
│  - Executes flows                       │
│  - Reports status                       │
│  - Manages concurrency                  │
└─────────────────────────────────────────┘
```

## Paths Reference

| Component | Path | Type |
|-----------|------|------|
| Dog | `dog.py` | Daemon |
| Specialists | `agents/specialists/*.md` | Static |
| Teams | `agents/teams/team-*.yaml` | Static |
| Flows | `agents/flows/<name>/<name>.yaml` | Static |
| Logic | `agents/flows/<name>/logic/*.py` | Static |
| Tasks | `tasks/<task-id>/` | Dynamic |
| Outputs | `tasks/<task-id>/outputs/*.json` | Dynamic |
| State | `tasks/<task-id>/state.db` | Dynamic |

## Current vs Target

**Current Implementation:**
- Outputs saved to flow directory (mixed static/dynamic)
- No task.json metadata
- /tmp/dog-runs/ for logs only

**Target Implementation:**
- Outputs saved to tasks/<id>/outputs/
- task.json with metadata and input parameters
- Clean flow directories (templates only)
- Dog as daemon receiving tasks
