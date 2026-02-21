# Rein OpenClaw Integration

Run [Rein](https://github.com/rein-orchestrator/rein) multi-agent workflows from [OpenClaw](https://github.com/nicepkg/openclaw) -- your personal AI assistant on Telegram, WhatsApp, Slack, Discord, and more.

## What this does

This package provides:

- **Plugin** (`src/`) -- registers 4 native tools in OpenClaw so the agent can call Rein with structured parameters
- **Skill** (`skills/rein/SKILL.md`) -- teaches the agent when and how to use the Rein tools

## Requirements

- Node.js >= 18
- Python >= 3.10 with `rein-ai` package installed (`pip install rein-ai[all]`)
- At least one AI provider configured (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)

## Installation

### 1. Build the plugin

```bash
cd integrations/openclaw
npm install
npm run build
```

### 2. Add to OpenClaw config

In your OpenClaw configuration (e.g. `openclaw.config.json`):

```json
{
  "plugins": [
    {
      "package": "@rein-ai/openclaw-plugin",
      "config": {
        "reinPath": "rein",
        "agentsDir": "/path/to/your/agents",
        "timeout": 600
      }
    }
  ]
}
```

### 3. Copy the skill

Copy the `skills/rein/` directory into your OpenClaw skills directory:

```bash
cp -r skills/rein/ /path/to/openclaw/skills/
```

### 4. Verify

Send a message to your OpenClaw bot:

> List available rein workflows

The agent should call `rein_list_flows` and show your available flows.

## Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `reinPath` | string | auto-detect | Path to `rein` CLI. Auto-detects from PATH, falls back to `python -m rein` |
| `agentsDir` | string | `REIN_AGENTS_DIR` env | Directory containing `flows/`, `specialists/`, `teams/` |
| `timeout` | number | 600 | Workflow execution timeout in seconds |

## Tools registered

| Tool | Description |
|------|-------------|
| `rein_list_flows` | List available workflows with descriptions and input schemas |
| `rein_run_workflow` | Execute a workflow synchronously and return results |
| `rein_create_task` | Create an async background task for the Rein daemon |
| `rein_task_status` | Check progress and outputs of a background task |

## Usage examples

**From any messenger connected to OpenClaw:**

> Run the deliberation flow on "Should we use Redis or PostgreSQL for caching?"

> Start a code review workflow for the auth module

> Check status of task-20260221-143022

## Architecture

```
OpenClaw Agent (any messenger)
     |
     v
  Plugin (this package)
     |
     v
  ReinClient (spawns subprocess)
     |
     v
  rein CLI (Python)
     |
     v
  Workflow execution (specialists + teams)
     |
     v
  Results returned to agent -> user
```

## Development

```bash
npm run dev    # Watch mode (rebuilds on change)
npm run build  # Production build
npm run clean  # Remove dist/
```

## License

MIT
