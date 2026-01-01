# Poetry Workflow Example - Dog MVP v1.0

**Dog Version:** MVP v1.0 (Tier 1, Python, Unix socket, SQLite)
**Date:** 2025-12-31
**Type:** Sequential workflow with dependencies

## Task

Create a 4-stanza poem with 2 alternating agents:
- **Agent 1 (rhymer):** Writes rhymed lines
- **Agent 2 (poet):** Writes lines with semantic meaning

**Output:** 8 lines total (4 stanzas x 2 lines each)
**Execution:** Sequential (one after another, not parallel)

## File 1: poem.yaml

Create this file:

```yaml
# Sequential poetry workflow
semaphore: 1            # One at a time (sequential)
timeout: 60             # Max 60 seconds per task

blocks:
  # Stage 1
  - name: stage-1-rhymer
    command: "python3 agent.py --type rhymer --stage 1"

  - name: stage-1-poet
    command: "python3 agent.py --type poet --stage 1"
    depends_on: stage-1-rhymer    # Wait for rhymer to finish

  # Stage 2
  - name: stage-2-rhymer
    command: "python3 agent.py --type rhymer --stage 2"
    depends_on: stage-1-poet      # Wait for poet to finish

  - name: stage-2-poet
    command: "python3 agent.py --type poet --stage 2"
    depends_on: stage-2-rhymer

  # Stage 3
  - name: stage-3-rhymer
    command: "python3 agent.py --type rhymer --stage 3"
    depends_on: stage-2-poet

  - name: stage-3-poet
    command: "python3 agent.py --type poet --stage 3"
    depends_on: stage-3-rhymer

  # Stage 4
  - name: stage-4-rhymer
    command: "python3 agent.py --type rhymer --stage 4"
    depends_on: stage-3-poet

  - name: stage-4-poet
    command: "python3 agent.py --type poet --stage 4"
    depends_on: stage-4-rhymer
```

## File 2: agent.py

Create this simple agent script:

```python
#!/usr/bin/env python3
"""
Simple poetry agent - writes lines for a poem.
Usage: python3 agent.py --type rhymer --stage 1
"""

import sys
import json
import argparse
from datetime import datetime

# Parse arguments
parser = argparse.ArgumentParser(description='Poetry agent')
parser.add_argument('--type', required=True, choices=['rhymer', 'poet'],
                    help='Agent type: rhymer (writes rhymed lines) or poet (writes semantic lines)')
parser.add_argument('--stage', type=int, required=True, choices=[1,2,3,4],
                    help='Stage number (1-4)')
args = parser.parse_args()

# Example lines for each stage
stages = {
    1: {
        'rhymer': 'Красивый день с рассветом',
        'poet': 'Приходит с утром свет'
    },
    2: {
        'rhymer': 'В лесу поёт волшебный птах',
        'poet': 'Душа поёт в стихах'
    },
    3: {
        'rhymer': 'Луна восходит в вышину',
        'poet': 'Сияет в ночь волшебно'
    },
    4: {
        'rhymer': 'И звёзды светят нам с небес',
        'poet': 'Приносит чудо каждый час'
    }
}

# Get the line for this agent and stage
agent_type = args.type
stage = args.stage
line = stages[stage][agent_type]

# Print to console
print(f"Stage {stage} ({agent_type}): {line}")

# Write result file (Dog verifies that this file was created)
result = {
    'stage': stage,
    'agent_type': agent_type,
    'line': line,
    'timestamp': datetime.now().isoformat()
}

filename = f'result-stage-{stage}-{agent_type}.json'
with open(filename, 'w') as f:
    json.dump(result, f, indent=2)

print(f"[OK] Wrote {filename}")
```

## How to Run

```bash
# 1. Go to Dog directory
cd /server/scripts/agent-pm2-dog

# 2. Create poem.yaml and agent.py (as shown above)

# 3. Run the workflow
./dog-cli.sh run poem.yaml

# 4. Watch it execute
./dog-cli.sh status
```

## What Happens

1. **Stage 1:** `stage-1-rhymer` runs → writes rhymed line
2. Dog waits for completion (depends_on)
3. **Stage 1:** `stage-1-poet` runs → writes semantic line
4. Dog waits for completion
5. **Stage 2:** `stage-2-rhymer` runs → writes rhymed line
6. ... (repeats for stages 3 and 4)
7. Final: 8 lines total in output

## Check Results

**Quick status:**
```bash
./dog-cli.sh status
```

**Full output and logs:**
```bash
./dog-cli.sh history 1 latest
```

**Look in logs directory:**
```bash
ls -la /tmp/dog-runs/run-*/logs/ | grep stage
```

## Key Concepts

| Parameter | Meaning |
|-----------|---------|
| `semaphore: 1` | Only 1 block runs at a time (sequential, not parallel) |
| `depends_on:` | Wait for this block to complete before starting |
| `command:` | Shell command to execute (Python script, bash script, anything) |
| `timeout:` | Kill block if it takes longer than this (in seconds) |

## Expected Output

In `/tmp/dog-runs/run-TIMESTAMP/dog.log`:

```
Stage 1 (rhymer): Красивый день с рассветом
Stage 1 (poet): Приходит с утром свет
Stage 2 (rhymer): В лесу поёт волшебный птах
Stage 2 (poet): Душа поёт в стихах
Stage 3 (rhymer): Луна восходит в вышину
Stage 3 (poet): Сияет в ночь волшебно
Stage 4 (rhymer): И звёзды светят нам с небес
Stage 4 (poet): Приносит чудо каждый час

[COMPLETE] 8/8 agents finished
```

## Variations

**Run in parallel (no dependencies):**
```yaml
semaphore: 8    # Allow up to 8 concurrent
# Remove all depends_on lines
```

**Run with 10 second delays:**
```yaml
- name: stage-1-rhymer
  command: "sleep 10 && python3 agent.py --type rhymer --stage 1"
```

**Run with timeout:**
```yaml
blocks:
  - name: stage-1-rhymer
    command: "python3 agent.py --type rhymer --stage 1"
    timeout: 30   # Kill if takes more than 30 seconds
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Database read error" | Normal for first run - SQLite may not be populated yet |
| "0/8 agents completed" | Check logs: `tail /tmp/dog-runs/run-*/dog.log` |
| Agent script not found | Make sure `agent.py` is in same directory as `poem.yaml` |
| Permission denied | Make scripts executable: `chmod +x agent.py` |

## Next Steps

1. Modify `agent.py` to generate **real** poem lines (not static)
2. Use Claude API to generate lines dynamically
3. Add feedback loop (poet reads what rhymer wrote)
4. Add aggregation step (compile all 8 lines into one file)

See: `PRODUCTION_GUIDE.md` for monitoring and `COMMANDS.md` for more examples.
