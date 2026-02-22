# Example 4: Deliberation

Three analysts debate a question through independent analysis, cross-review, and synthesis.

## What it does

A structured 3-phase deliberation process:

1. **Phase 1** -- Three analysts independently analyze the question (parallel)
2. **Phase 2** -- Each analyst reviews the other two's work (parallel, with cross-dependencies)
3. **Phase 3** -- Final consolidated recommendation

## Execution flow

```
Phase 1 (parallel):        Phase 2 (cross-review):       Phase 3:
strategic_analysis --+---> strategic_review  --\
                     |                          \
technical_analysis --+---> technical_review  ----+--> final_recommendation
                     |                          /
practical_analysis --+---> practical_review  --/
```

## Structure

```
04-deliberation/
  workflow.yaml
  agents/
    specialists/
      analyst-strategic.md
      analyst-technical.md
      analyst-practical.md
    teams/
      team-deliberation.yaml
```

## Run it

```bash
export ANTHROPIC_API_KEY=sk-...
rein --agents-dir ./agents workflow.yaml --no-ui
```

## Key concepts

- **Multi-phase workflows**: `phase: 1`, `phase: 2`, `phase: 3` organize blocks visually
- **Cross-dependencies**: Phase 2 blocks depend on Phase 1 outputs from *other* specialists
- **Structured debate**: Each analyst sees others' work and can update their position
- **Convergence**: The final block synthesizes all perspectives into one decision
