[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://github.com/rein-orchestrator/rein/actions/workflows/test.yml/badge.svg)](https://github.com/rein-orchestrator/rein/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/rein-ai.svg)](https://pypi.org/project/rein-ai/)

# Rein

![Rein Flow Board](https://github.com/dklymentiev/rein-orchestrator/releases/download/v3.3.2/rein-demo.gif)

**Give a complex task to a team of AI agents instead of just one.**

Instead of writing a single massive prompt, you break work into steps and assign each step to a specialist -- a researcher, a writer, an editor. Each one gets the previous agent's output automatically. They can work in parallel, loop back for revisions, and make decisions based on results.

You describe *what* should happen in plain text files (YAML + Markdown). Rein figures out the *how* -- launches agents, passes data between them, tracks progress, handles failures.

Works with any LLM: Claude, GPT, Ollama (local/free), OpenRouter (100+ models). No Python code required.

## The Problem

You paste a 2000-word prompt into Claude. It researches, writes, edits, and fact-checks -- all in one shot. The result is mediocre at everything because one agent can't be an expert at everything simultaneously.

You know the fix: break it into steps. But then you're manually copying outputs between chats, tracking what depends on what, restarting when something fails halfway through.

Rein fixes this. You define specialists in Markdown, wire them together in YAML, and run a single command. Each agent focuses on what it does best, gets exactly the context it needs, and hands off to the next one automatically.

## The Solution

```yaml
# workflow.yaml
provider: anthropic
model: claude-sonnet-4-20250514
team: my-team

blocks:
  - name: research
    specialist: researcher
    prompt: "Analyze this topic: {{ task.input.topic }}"

  - name: write
    specialist: writer
    depends_on: [research]
    prompt: "Write article based on: {{ research.json }}"

  - name: edit
    specialist: editor
    depends_on: [write]
    prompt: "Polish and fact-check: {{ write.json }}"
```

No Python classes. No framework APIs. No graph DSLs. Just text files that describe what each agent does and how they connect.

## Quick Start

```bash
# Install
pip install rein-ai[anthropic]

# Set your API key
export ANTHROPIC_API_KEY=sk-...

# Run the hello-world example
cd examples/01-hello-world
rein --agents-dir ./agents workflow.yaml --no-ui
```

```
# Output:
# [research]  done  3.2s  researcher  "Found 12 relevant sources on AI trends"
# [write]     done  5.1s  writer      "Draft complete: 1,847 words"
# [edit]      done  2.8s  editor      "Fixed 3 issues, polished to 1,923 words"
#
# Result: /tmp/rein-runs/run-20260321/write/outputs/result.json
```

For a step-by-step tutorial that walks you through creating specialists, teams, and workflows from scratch, see the **[Getting Started Guide](docs/getting-started.md)**.

## How It Works

Rein has a 3-layer architecture -- all defined in text files:

```
Layer 1: SPECIALISTS (Markdown)     What each AI agent does
Layer 2: TEAMS (YAML)               Groups of specialists + shared tone
Layer 3: WORKFLOWS (YAML)           Execution flow with dependencies
```

**Specialist** -- a Markdown file defining an AI agent's role:

```markdown
# Code Reviewer

You are a senior engineer conducting code reviews.

## Output Format
{"verdict": "approve|request_changes", "issues": [...]}
```

**Team** -- a YAML file grouping specialists:

```yaml
name: code-review-team
specialists:
  - code-reviewer
  - code-improver
collaboration_tone: |
  Be constructive and specific. Always output valid JSON.
```

**Workflow** -- a YAML file defining what to execute:

```yaml
blocks:
  - name: review
    specialist: code-reviewer
    prompt: "Review this code: ..."

  - name: improve
    specialist: code-improver
    depends_on: [review]
    prompt: "Fix issues found: {{ review.json }}"
```

## Who Is This For

- **Solo developers** who want structured AI workflows without writing Python
- **Teams** that need repeatable, auditable AI processes
- **Anyone tired of copy-pasting between chat windows** to get multi-step work done

If you can edit a YAML file, you can orchestrate a team of AI agents.

## Comparison

| | Rein | CrewAI | LangGraph | AutoGen |
|---|---|---|---|---|
| Config format | YAML + Markdown | Python classes | Python code | Python code |
| Code required | No | Yes | Yes | Yes |
| LLM providers | 4+ (Claude, GPT, Ollama, OpenRouter) | Limited | Limited | Limited |
| Crash recovery | SQLite state | No | Checkpointing | No |
| MCP server | Built-in | No | No | No |
| Local/free models | Ollama | Limited | No | No |
| Learning curve | Edit YAML files | Learn framework API | Learn graph DSL | Learn agent API |

## Examples

Five progressive examples in the `examples/` directory:

| # | Example | Pattern | What you learn |
|---|---------|---------|----------------|
| 01 | [hello-world](examples/01-hello-world/) | 1 specialist | Basics: specialist, team, workflow |
| 02 | [code-review](examples/02-code-review/) | 2 sequential | Dependencies and data flow |
| 03 | [research-team](examples/03-research-team/) | 3 parallel + 1 | Fan-out / fan-in pattern |
| 04 | [deliberation](examples/04-deliberation/) | 3-phase debate | Cross-review and multi-phase |
| 05 | [conditional](examples/05-conditional/) | Branching + loops | if/else, revision loops, max_runs |

```bash
# Try any example
cd examples/03-research-team
export ANTHROPIC_API_KEY=sk-...
rein --agents-dir ./agents workflow.yaml --no-ui
```

## Installation

```bash
# Core (picks provider from environment)
pip install rein-ai

# With specific provider SDK
pip install rein-ai[anthropic]    # Claude (anthropic SDK)
pip install rein-ai[openai]       # GPT-4o (openai SDK)
pip install rein-ai[all]          # Both SDK-based providers (anthropic + openai)

# Ollama and OpenRouter providers use the `requests` library that is
# already part of the base install -- no extras needed.

# For daemon mode (WebSocket support)
pip install rein-ai[daemon]

# For MCP server (Claude Desktop, Cursor, Claude Code)
pip install rein-ai[mcp]
```

Or from source:

```bash
git clone https://github.com/rein-orchestrator/rein.git
cd rein
pip install -e ".[dev]"
```

## Provider Configuration

Set your provider in workflow YAML and API key in environment:

```yaml
# Anthropic Claude
provider: anthropic
model: claude-sonnet-4-20250514
```

```yaml
# OpenAI
provider: openai
model: gpt-4o
```

```yaml
# Ollama (local, no API key needed)
provider: ollama
model: llama3.1
```

```yaml
# OpenRouter (100+ models)
provider: openrouter
model: anthropic/claude-sonnet-4-20250514
```

Environment variables:

| Provider | Env Variable | Required |
|----------|-------------|----------|
| anthropic | `ANTHROPIC_API_KEY` | Yes |
| openai | `OPENAI_API_KEY` | Yes |
| ollama | `OLLAMA_URL` | No (default: localhost:11434) |
| openrouter | `OPENROUTER_API_KEY` | Yes |
| gateway | `AI_GATEWAY_URL` or `BRAIN_API_URL` | Yes |

Auto-detection: if no `provider:` is set in YAML, Rein checks environment variables in order: `ANTHROPIC_API_KEY` -> `OPENAI_API_KEY` -> `OPENROUTER_API_KEY` -> `OLLAMA_URL` -> `AI_GATEWAY_URL`.

Copy `.env.example` to `.env` and fill in your preferred provider key:

```bash
cp .env.example .env
```

## Workflow Features

### Dependencies and Parallelism

Blocks with no dependencies run in parallel. `max_parallel` limits concurrency.

```yaml
max_parallel: 3

blocks:
  - name: a
    prompt: "..."         # Runs immediately

  - name: b
    prompt: "..."         # Runs in parallel with a

  - name: c
    depends_on: [a, b]    # Waits for both a and b
    prompt: "{{ a.json }} {{ b.json }}"
```

### Conditional Branching

Route execution based on block output:

```yaml
- name: gate
  prompt: "Evaluate quality..."
  next:
    - if: "{{ result.approved }}"
      goto: publish
    - else: revision
```

Condition syntax: `{{ result.field }}` (truthy), `{{ result.score > 0.8 }}` (comparison), `{{ result.status == 'done' }}` (equality).

### Revision Loops

Send a block back for re-evaluation with loop protection:

```yaml
- name: revision
  depends_on: [gate]
  max_runs: 3            # Max 3 attempts
  next: gate             # Back to quality check
```

### Logic Scripts

Python scripts for pre/post processing:

```yaml
logic:
  pre: logic/fetch-data.py       # Before LLM: prepare data
  post: logic/save-result.py     # After LLM: process output
  validate: logic/check.py       # Gate: exit code 0 = pass
  custom: true                   # Skip LLM entirely
```

Scripts receive JSON context via stdin:

```json
{
  "output_file": "path/to/result.json",
  "block_dir": "path/to/block/",
  "task_input": {"topic": "..."},
  "task_id": "task-20260102-183805",
  "workflow_dir": "path/to/flow/",
  "run_count": 0,
  "depends_on": ["block_a", "block_b"],
  "block_config": { "name": "my_block", "phase": 2 }
}
```

When `logic.custom` is a string (script path), it replaces the LLM call entirely:

```yaml
logic:
  custom: "logic/my-script.py"    # Runs this instead of calling LLM
```

When `logic.custom: true` (boolean), the pre-phase script handles everything and LLM is skipped.

### Tag-Based Routing (v3.3)

Route execution based on signals in block output. Scripts print `VERDICT: <signal>` to stdout, and routing matches the signal:

```yaml
- name: qa_gate
  depends_on: [tests, review]
  logic:
    custom: "logic/evaluate.py"
  routing:
    revise: fix_block          # VERDICT: REVISE -> go to fix_block
    needs-review: reviewer     # VERDICT: PASS or VERDICT: APPROVED -> needs-review
    _default: release          # No signal matched -> default path
  max_runs: 3                  # Max 3 routing cycles
```

Signal extraction: orchestrator reads `VERDICT:` lines from block result. `PASS`/`APPROVED` maps to `needs-review`, `REVISE` maps to `revise`.

Routing resets the target block and cascade-invalidates all blocks that depend on it.

### Error Handling

Global error handler runs when any block fails:

```yaml
on_error: logic/notify-failure.py
```

Per-block error handler runs before the global handler:

```yaml
- name: deploy
  logic:
    custom: "logic/deploy.sh"
    error: "logic/rollback.sh"     # Runs if deploy fails
```

### Execution Phases

The `phase` field controls execution order. Blocks in the same phase with satisfied dependencies run in parallel:

```yaml
blocks:
  - name: research
    phase: 1                       # Runs first

  - name: analysis
    phase: 2
    depends_on: [research]         # Runs after phase 1

  - name: report
    phase: 3
    depends_on: [analysis]
```

Phases are optional -- without them, execution order is determined purely by `depends_on`.

### Flow Control Flags

```yaml
- name: optional_check
  skip_if_previous_failed: true    # Skip if any dependency failed
  continue_if_failed: true         # Don't fail the workflow if this block fails
```

### Declarative Inputs (v2.6)

Validate task input before execution starts:

```yaml
inputs:
  topic:
    description: "What to research"
    required: true
  style:
    description: "Writing style"
    required: false
    default: "professional"
```

Referenced in prompts as `{{ task.input.topic }}`.

### Block-Level Model Override

Override the LLM model for specific blocks:

```yaml
- name: simple_task
  model: "haiku"                   # Use faster/cheaper model
  prompt: "Summarize..."

- name: complex_analysis
  model: "opus"                    # Use most capable model
  prompt: "Deep analysis..."
```

### Custom Output Filenames

```yaml
- name: generate_report
  save_as: "report.md"            # Save output as report.md instead of result.json
```

### Workflow-Level Settings

```yaml
readable_outputs: true             # Save human-readable .md alongside JSON
timeout: 3600                      # Workflow timeout in seconds (30-86400)
metadata:
  version: "1.0"
  author: "team"
  created: "2026-01-15"
```

### Template Variables

Reference previous block outputs and task input in prompts:

```yaml
prompt: |
  Topic: {{ task.input.topic }}
  Research: {{ research.json }}
  Review: {{ review.json }}
```

## MCP Server

Rein includes an MCP (Model Context Protocol) server, so you can run workflows directly from Claude Desktop, Cursor, Claude Code, or any MCP-compatible client.

```bash
pip install rein-ai[mcp]
```

### Claude Desktop / Cursor

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "rein": {
      "command": "rein-mcp",
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "REIN_AGENTS_DIR": "/path/to/your/agents"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add rein -- rein-mcp
```

### Available Tools

| Tool | Description |
|------|-------------|
| `list_flows` | List available workflows with descriptions and block counts |
| `list_specialists` | List specialists with summaries |
| `list_teams` | List teams and their composition |
| `run_workflow` | Execute a workflow synchronously and return results |
| `create_task` | Create an async task for the daemon |
| `task_status` | Check task progress (block-level detail) |
| `list_tasks` | List recent tasks with status |

The MCP server also supports SSE and streamable-http transports:

```bash
rein-mcp --sse          # SSE transport
rein-mcp --streamable-http  # HTTP streaming
```

## Daemon Mode

Run Rein as a background service that watches for tasks:

```bash
rein --daemon --agents-dir ./agents --ws-port 8765
```

The daemon monitors `agents/tasks/` for directories with `state/status = "pending"` and executes them automatically. Live updates are broadcast via WebSocket on the configured port.

For systemd deployment, see `deploy/rein-daemon.service`.

## Terminal UI

When running without `--no-ui`, Rein displays an htop-like interface:

- Block name, status (running/done/failed/waiting), progress bar
- Flags: P=parallel, D=deps, L=logic, N=next, R=max_runs
- IN/OUT data sizes, elapsed time

Runtime controls (via stdin): `p` = pause, `r` = resume, `q` = quit.

## Step Mode (v3.3)

By default, `rein` runs all blocks in one process. **Step mode** runs a fixed number of blocks per invocation, saves progress, and exits. This enables cron-driven execution, multi-agent pipelines, and human review between steps.

```bash
# Run 1 block at a time
rein --flow my-flow --step 1 --input '{"topic":"AI"}'
# Exit code: 0 = done, 2 = more steps remain

# Resume -- runs next block
rein --step 1 --task-dir /agents/tasks/task-20260402-170000

# Run up to 5 blocks (parallel if dependencies allow)
rein --step 5 --task-dir /agents/tasks/task-20260402-170000

# Run all remaining blocks
rein --step 0 --task-dir /agents/tasks/task-20260402-170000
```

### Multi-Agent Routing

Different agents can execute different blocks. Add `agent:` to your workflow blocks:

```yaml
blocks:
  - name: draft
    agent: smm
    prompt: "Write a post about {{ task.input.topic }}"
  - name: review
    agent: editor
    depends_on: [draft]
    prompt: "Review: {{ draft.json }}"
```

Each agent uses `--agent-id` to identify itself:

```bash
# SMM agent's cron -- only runs blocks with agent: smm
rein --step 1 --task-dir task-2000 --agent-id smm

# Editor's cron -- only runs blocks with agent: editor
rein --step 1 --task-dir task-2000 --agent-id editor
```

Blocks without `agent:` run for any agent. Without `--agent-id`, all blocks run.

## CLI and Directory Structure

For the full CLI reference and directory layout, see [docs/getting-started.md](docs/getting-started.md).

Quick reference:

```bash
# Continuous mode (run all blocks)
rein workflow.yaml --agents-dir ./agents   # Run a workflow
rein --flow deliberation --question q.txt  # Run a named flow
rein --resume 20260113-143022              # Resume a failed run

# Step mode (run N blocks, save state, exit)
rein --flow my-flow --step 1               # First invocation
rein --step 3 --task-dir /path/to/task     # Resume, run 3 blocks
rein --step 1 --task-dir /path --agent-id smm  # Agent-specific

# Background
rein --daemon --agents-dir ./agents        # Daemon mode
```

## Tech Stack

- Python 3.10+
- Rich (terminal UI)
- SQLite (state persistence, crash recovery)
- YAML (workflow definitions)
- Markdown (specialist prompts)

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

For security issues, please see [SECURITY.md](SECURITY.md).

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).

## License

MIT

---

Created by [Dmytro Klymentiev](https://klymentiev.com)
