# Example 3: Research Team

Three specialists research in parallel, then a synthesizer consolidates their findings.

## What it does

1. **market-analyst**, **tech-analyst**, and **user-researcher** run simultaneously (no dependencies between them)
2. **synthesizer** waits for all three to finish, then produces a unified recommendation

This demonstrates the **fan-out / fan-in** pattern.

## Execution flow

```
market_analysis ---\
tech_analysis   ----+--> synthesis
user_analysis   ---/
```

## Structure

```
03-research-team/
  workflow.yaml
  agents/
    specialists/
      market-analyst.md
      tech-analyst.md
      user-researcher.md
      synthesizer.md
    teams/
      team-research.yaml
```

## Run it

```bash
export ANTHROPIC_API_KEY=sk-...
rein --agents-dir ./agents workflow.yaml --no-ui
```

## Key concepts

- **Parallel execution**: Blocks with no `depends_on` each other run simultaneously
- **`max_parallel: 3`**: Up to 3 blocks can run at the same time
- **Fan-in**: `depends_on: [market_analysis, tech_analysis, user_analysis]` waits for ALL to complete
- **Data aggregation**: The synthesizer's prompt includes all three outputs via `{{ name.json }}`
