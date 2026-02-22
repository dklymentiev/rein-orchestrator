# Example 08: Generic Deliberation

Creator/Critic/Integrator deliberation pattern -- a reusable template for any problem-solving task.

## What You'll Learn

- **Creator-Critic-Integrator pattern**: The most versatile deliberation structure
- **Role separation**: Ideas, critique, and synthesis handled by different specialists
- **Cross-review**: Each role evaluates the others' contributions
- **Reusable template**: Adapt this workflow for any problem domain

## How It Works

```
Phase 1: Independent Proposals (parallel)
  creator_proposal    -- multiple solution approaches
  critic_proposal     -- risk analysis and edge cases
  integrator_proposal -- requirements and success criteria

Phase 2: Cross-Review (parallel)
  creator_review    -- updates proposals based on risks/constraints
  critic_review     -- evaluates proposals against risk analysis
  integrator_review -- assesses feasibility and integration

Phase 3: Final Synthesis
  final_plan        -- unified implementation plan
```

## Structure

```
08-generic-deliberation/
  workflow.yaml
  agents/
    specialists/
      creator-specialist.md     -- Generates solution proposals
      critic-specialist.md      -- Finds risks and problems
      integrator-specialist.md  -- Synthesizes and decides
    teams/
      team-generic.yaml
```

## Run

```bash
cd examples/08-generic-deliberation
rein --agents-dir ./agents workflow.yaml --no-ui \
  --input '{"task": "Design a caching layer for a REST API serving 10k requests/minute"}'
```

## Key Pattern: Creator-Critic-Integrator

This is the foundational deliberation pattern:

- **Creator** thinks expansively: "What are all the ways to solve this?"
- **Critic** thinks defensively: "What could go wrong?"
- **Integrator** thinks pragmatically: "What should we actually do?"

The tension between these roles produces better solutions than any single perspective.

## Adapting This Template

This is designed as a starting point. To customize:

1. **Change the specialists** -- swap in domain-specific experts
2. **Add phases** -- insert a Phase 2.5 for deeper review
3. **Add blocks** -- include more specialists in Phase 1
4. **Change the final synthesizer** -- use a different specialist for consolidation

## 7 Blocks, 3 Specialists

| Block | Specialist | Phase | Depends On |
|-------|-----------|-------|------------|
| creator_proposal | creator-specialist | 1 | -- |
| critic_proposal | critic-specialist | 1 | -- |
| integrator_proposal | integrator-specialist | 1 | -- |
| creator_review | creator-specialist | 2 | critic, integrator |
| critic_review | critic-specialist | 2 | creator, integrator |
| integrator_review | integrator-specialist | 2 | creator, critic |
| final_plan | integrator-specialist | 3 | all reviews |
