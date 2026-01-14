# Rein

Workflow orchestrator for multi-agent AI - like PM2 but for Claude specialists.

**Status:** Production | **Version:** 3.3.0 (2026-01-13)

## Problem Solved

December 2025. Running multiple Claude agents in parallel. No coordination - agents stepping on each other, API rate limits hit randomly, no way to track what finished or failed. Needed something like PM2 or htop but for AI workflows.

## Core Concept

**Declarative + Runtime Architecture:**
- **Declarations (text files):** Specialists (.md), Teams (.yaml), Workflows (.yaml)
- **Runtime (system process):** Rein reads declarations, executes workflows, accepts commands via Unix socket

Edit YAML -> Rein picks it up. No compilation. No restart. Text in, AI orchestration out.

## Architecture

```
TEXT DECLARATIONS                    RUNTIME PROCESS
-----------------                    ---------------
Specialists (.md)  -+
Teams (.yaml)      -+-->  Rein Process  <-->  Unix Socket (/tmp/rein-{guid}.sock)
Workflows (.yaml)  -+         |                    ^
Logic scripts (.py)           v              rein-cmd.sh (CLI client)
                     Claude API + SQLite
```

## Directory Structure (v3.0)

```
/server/agents/
|-- flows/                      # Workflow templates (no data)
|   +-- blog-publication/
|       |-- blog-publication.yaml
|       |-- .env                # Per-flow API config
|       +-- logic/
|           |-- search-memory.py
|           +-- publish-article.py
|
|-- specialists/                # Reusable agent prompts
|   |-- blog-researcher.md
|   |-- blog-writer.md
|   +-- blog-censor.md
|
|-- teams/                      # Team configurations
|   +-- team-blog.yaml
|
+-- tasks/                      # Workflow executions (data)
    +-- task-20260102-183805/
        |-- input/
        |   +-- task.json       # Input parameters
        |-- state/
        |   |-- status          # completed/running/failed
        |   |-- rein.log        # Execution log
        |   +-- rein.db         # SQLite state
        +-- research/           # Block directories (v3.0)
        |   |-- inputs/
        |   |-- outputs/
        |   |   +-- result.json
        |   +-- logs/
        +-- draft/
            |-- inputs/
            |-- outputs/
            |   +-- result.json
            +-- logs/
```

## Key Features

| Feature | Description |
|---------|-------------|
| **Semaphore Control** | Limit concurrent API calls (don't burn rate limits) |
| **Dependency Graph** | Blocks wait for dependencies, auto-parallel when possible |
| **Specialist System** | Reusable agent prompts in .md files, teams set tone |
| **State Machine** | Conditional transitions (if/else/goto), revision loops with max_runs |
| **Block Isolation** | Each block gets own directory with inputs/outputs/logs (v3.0) |
| **Logic Scripts** | Python scripts for phases: pre, post, validate, custom |
| **Visual Monitoring** | htop-like terminal UI with FLAGS and IN/OUT columns |
| **Runtime Control** | Pause/resume/cancel blocks or entire workflow |
| **Socket API** | Unix domain socket for external integrations |
| **SQLite State** | Crash recovery, resume from last checkpoint |
| **Schema Validation** | JSON Schema + Pydantic validation before execution |

## CLI Reference

### Basic Usage

```bash
# Simplest way - flow name + question text
python3 rein.py --flow deliberation --question "Should we use Redis or PostgreSQL?"

# With JSON input (for complex parameters)
python3 rein.py --flow blog-publication --input '{"topic": "semantic search", "style": "technical"}'

# Run existing task directory
python3 rein.py --task /server/agents/tasks/task-20260113-143022

# Check task status
python3 rein.py --status task-20260113-143022
```

### All CLI Options

| Option | Description | Example |
|--------|-------------|---------|
| `--flow NAME` | Flow name from /server/agents/flows/ | `--flow deliberation` |
| `--question TEXT` | Simple question/topic (auto-creates task) | `--question "How to improve API?"` |
| `--input JSON` | JSON parameters for task.input | `--input '{"topic": "...", "count": 5}'` |
| `--task DIR` | Run existing task directory | `--task /server/agents/tasks/task-001` |
| `--task-dir DIR` | Directory with task.md file | `--task-dir /path/to/my-task` |
| `--status ID` | Show task status | `--status task-20260113-143022` |
| `--resume ID` | Resume previous run | `--resume 20260113-143022` |
| `--pause` | Start in paused state | `--pause` |
| `--no-ui` | Disable Rich terminal UI | `--no-ui` |
| `--agents-dir PATH` | Custom agents directory | `--agents-dir /my/agents` |
| `config` | Direct path to YAML file | `rein.py workflow.yaml` |

### How Task is Created

When you run with `--flow` + `--question` or `--input`:

1. Rein creates task directory:
```
/server/agents/tasks/task-20260113-143022/
├── input/
│   └── task.json      # {"topic": "your question"}
├── output/            # Final results
├── state/
│   ├── status         # pending -> running -> completed
│   ├── rein.db        # SQLite state
│   └── rein.log       # Execution log
└── {block_name}/      # Directory per block
    └── outputs/
        └── result.json
```

2. Loads flow YAML from `/server/agents/flows/{name}/{name}.yaml`
3. Replaces `{{ task.input.topic }}` with your question
4. Executes blocks according to dependencies

### Input Methods

**Simple question (recommended for single-topic flows):**
```bash
python3 rein.py --flow deliberation --question "What database should we use?"
```
Creates: `{"topic": "What database should we use?"}`

**JSON input (for multiple parameters):**
```bash
python3 rein.py --flow blog-publication --input '{"topic": "AI trends", "style": "casual", "max_words": 1000}'
```
Creates: `{"topic": "AI trends", "style": "casual", "max_words": 1000}`

**From task directory (pre-created):**
```bash
# Create task manually
mkdir -p /server/agents/tasks/my-task/input
echo '{"topic": "My question"}' > /server/agents/tasks/my-task/input/task.json

# Run it
python3 rein.py --task /server/agents/tasks/my-task
```

### Monitoring Running Task

```bash
# Check status
python3 rein.py --status task-20260113-143022

# Watch log
tail -f /server/agents/tasks/task-20260113-143022/state/rein.log

# Runtime control (while running)
./rein-cmd.sh status
./rein-cmd.sh pause block-name
./rein-cmd.sh resume block-name
```

### Quick Start Examples

```bash
# Simple deliberation
python3 rein.py --flow deliberation --question "Should we use Redis or PostgreSQL?"

# Blog post generation
python3 rein.py --flow blog-publication --input '{"topic": "semantic search"}'

# Resume failed task
python3 rein.py --resume 20260113-143022

# Run without terminal UI (for scripts/cron)
python3 rein.py --flow deliberation --question "Test" --no-ui
```

## Workflow Example

```yaml
schema_version: "3.0.0"
name: blog-publication
team: team-blog
max_parallel: 2

blocks:
  - name: research
    specialist: blog-researcher
    prompt: "Research topic: {{ task.input.topic }}"
    logic:
      pre: logic/search-memory.py

  - name: draft
    specialist: blog-writer
    depends_on: [research]
    prompt: "Write article based on: {{ research.json }}"

  - name: censor
    specialist: blog-censor
    depends_on: [draft]
    prompt: "Review article: {{ draft.json }}"
    next:
      - if: "{{ result.approved }}"
        goto: publish
      - else: revision

  - name: revision
    specialist: blog-editor
    depends_on: [censor]
    max_runs: 2                    # Loop protection
    next: censor                   # Back to censor

  - name: publish
    specialist: blog-publisher
    depends_on: [censor]
    logic:
      post: logic/publish-article.py
```

## Logic Scripts

Scripts receive JSON context via stdin:

```json
{
  "output_file": "/path/to/block/outputs/result.json",
  "block_dir": "/path/to/task/block/",
  "block_config": { "name": "...", "prompt": "..." },
  "outputs_dir": "/path/to/task/block/outputs/",
  "task_input": { "topic": "..." },
  "task_id": "task-20260102-183805",
  "workflow_dir": "/path/to/flow/"
}
```

**Example script (aggregate.py):**

```python
#!/usr/bin/env python3
import json, sys, os
from pathlib import Path

context = json.loads(sys.stdin.read())
task_dir = Path(context['block_dir']).parent

# Read dependencies by name (v3.0 structure)
dep_result = task_dir / "research" / "outputs" / "result.json"
data = json.load(open(dep_result))

result = {"stage": "aggregate", "result": {"total": data['result']['value']}}

with open(context['output_file'], 'w') as f:
    json.dump(result, f, indent=2)

print(f"[OK] Aggregated")
```

**Logic phases:**

```yaml
logic:
  pre: logic/fetch-data.py       # Before Claude: prepare data
  post: logic/save-result.py     # After Claude: process output
  validate: logic/check.py       # Gate: return exit code 0/1
  custom: true                   # Skip Claude, pre script does everything
  custom: logic/run-llm.py       # Replace Claude with custom script
```

## State Machine Flow

**Conditional transitions:**

```yaml
next:
  - if: "{{ result.approved }}"
    goto: publish
  - if: "{{ result.score > 0.8 }}"
    goto: fast_track
  - else: revision
```

**Condition syntax:**
- Truthy: `{{ result.approved }}`
- Equality: `{{ result.status == 'done' }}`
- Comparison: `{{ result.score > 0.8 }}`
- Nested: `{{ result.data.count >= 10 }}`

**Loop protection:**

```yaml
- name: revision
  max_runs: 3          # Max 3 revision cycles
  next: review         # Then back to review
```

## Runtime Control

```bash
# While workflow is running:
./rein-cmd.sh status              # Current state
./rein-cmd.sh list                # All processes with UIDs
./rein-cmd.sh pause block-1       # Pause specific block
./rein-cmd.sh resume block-1      # Resume block
./rein-cmd.sh cancel block-1      # Kill block
./rein-cmd.sh pause-workflow      # Pause everything
./rein-cmd.sh resume-workflow     # Resume everything

# Monitoring
./rein-workflows.sh               # List active workflows
./rein-status.sh                  # Detailed status
watch -n 2 './rein-workflows.sh'  # Real-time updates
```

## UI Columns

The terminal UI shows:
- **Name:** Block name (16 chars)
- **Status:** running/done/failed/waiting
- **Flags:** P=parallel D=deps L=logic N=next S=skip C=continue R=max_runs
- **IN/OUT:** Input/output data sizes (e.g., "1.2K/0.8K")
- **Progress:** Progress bar
- **Time:** Elapsed time

## Flow Control Parameters

```yaml
blocks:
  - name: critical_step
    continue_if_failed: false    # Stop workflow if this fails

  - name: optional_step
    continue_if_failed: true     # Continue even if fails (default)
    skip_if_previous_failed: true  # Run even if earlier blocks failed
```

## Schema Validation

Workflows are validated before execution:

```bash
# Validate workflow
python3 -c "
from models.validator import ValidationEngine
v = ValidationEngine()
result = v.validate_workflow('agents/flows/my-flow/my-flow.yaml')
print(result)
"
```

**Schema files:**
- `schemas/workflow-v3.0.0.json` - Workflow structure
- `schemas/team-v2.5.3.json` - Team structure
- `schemas/registry.json` - Version compatibility matrix

## Tech Stack

- Python 3.10+ (~1900 lines in modular package)
- Rich (terminal UI)
- SQLite (state persistence)
- Unix domain sockets (runtime control)
- Anthropic SDK / OpenRouter (Claude API)
- Pydantic + JSON Schema (validation)

## Metrics

- 50-block workflow: ~3 minutes (parallel arithmetic test)
- 10-block deliberation: ~15 minutes (4 Claude API calls per block)
- ~30MB base memory + 5-10MB per 100 tasks
- ~1900 lines Python (vs 50k+ for alternatives)

## Limitations

- Single machine only (not distributed)
- Tested up to 50 blocks (need to test 500+)

## Planned: v3.4+

- **Retry logic:** `retry: 3` with exponential backoff
- **Resource pools:** `max_concurrent: 5` per resource type
- **Notifications:** Telegram alerts on events
- **Heartbeat:** Watchdog for hung processes
- **Checkpointing:** Resume long operations
- **Together AI:** Additional LLM provider support

---

See CHANGELOG.md for version history.
