# Example 5: Conditional Workflow

Demonstrates if/else branching, revision loops, and `max_runs` limits.

## What it does

1. **writer** produces a draft article
2. **quality-gate** evaluates it -- approve or reject
3. If **rejected**: **writer** revises based on feedback, then back to quality gate (max 2 revisions)
4. If **approved**: **formatter** prepares for publication

## Execution flow

```
draft --> quality_check --[approved]--> format
               |
               +--[rejected]--> revision ---> quality_check (loop)
                                  |
                                  max_runs: 2 (prevents infinite loops)
```

## Structure

```
05-conditional/
  workflow.yaml
  agents/
    specialists/
      writer.md
      quality-gate.md
      formatter.md
    teams/
      team-editorial.yaml
```

## Run it

```bash
export ANTHROPIC_API_KEY=sk-...
rein --agents-dir ./agents workflow.yaml --no-ui
```

## Key concepts

- **Conditional branching**: `next:` with `if/else` directs flow based on output
- **Revision loops**: `next: quality_check` sends the block back for re-evaluation
- **`max_runs: 2`**: Prevents infinite loops -- after 2 revisions, the workflow moves on
- **`{{ result.approved }}`**: References the current block's output for branching decisions
