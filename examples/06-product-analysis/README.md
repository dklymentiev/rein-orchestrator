# Example 06: Product Analysis

Multi-role product analysis with Product Manager, UX Researcher, and Business Analyst perspectives across 4 deliberation phases.

## What You'll Learn

- **Multi-phase deliberation**: 4-phase pattern (analyze -> cross-review -> synthesize -> consolidate)
- **Role-based perspectives**: Three specialists analyze the same question from different angles
- **Cross-review**: Each specialist reads and critiques the others' work
- **Parallel execution**: Independent blocks run simultaneously within each phase

## How It Works

```
Phase 1: Independent Analysis (parallel)
  analyst_1_initial (Product Manager)
  analyst_2_initial (UX Researcher)
  analyst_3_initial (Business Analyst)

Phase 2: Cross-Review (parallel)
  analyst_1_review  -- reads analyst_2 + analyst_3
  analyst_2_review  -- reads analyst_1 + analyst_3
  analyst_3_review  -- reads analyst_1 + analyst_2

Phase 3: Synthesis (parallel)
  analyst_1_synthesis -- integrates all reviews
  analyst_2_synthesis
  analyst_3_synthesis

Phase 4: Final Consolidation
  final_recommendation -- unified decision
```

## Structure

```
06-product-analysis/
  workflow.yaml
  agents/
    specialists/
      product-manager.md    -- User value and business outcomes
      ux-researcher.md      -- Interface elements and user journey
      business-analyst.md   -- Requirements and compliance
    teams/
      team-product.yaml
```

## Run

```bash
cd examples/06-product-analysis
rein --agents-dir ./agents workflow.yaml --no-ui \
  --input '{"topic": "Should we add social login to our SaaS product?"}'
```

## Key Pattern: 4-Phase Deliberation

This is the most thorough deliberation pattern in Rein:

1. **Independent analysis** -- prevents groupthink, each specialist thinks alone
2. **Cross-review** -- specialists challenge each other's assumptions
3. **Synthesis** -- each specialist integrates feedback into refined position
4. **Consolidation** -- one specialist creates the unified team recommendation

Use this pattern when you need high-quality decisions with multiple stakeholder perspectives.

## 10 Blocks, 3 Specialists

| Block | Specialist | Phase | Depends On |
|-------|-----------|-------|------------|
| analyst_1_initial | product-manager | 1 | -- |
| analyst_2_initial | ux-researcher | 1 | -- |
| analyst_3_initial | business-analyst | 1 | -- |
| analyst_1_review | product-manager | 2 | analyst_2, analyst_3 |
| analyst_2_review | ux-researcher | 2 | analyst_1, analyst_3 |
| analyst_3_review | business-analyst | 2 | analyst_1, analyst_2 |
| analyst_1_synthesis | product-manager | 3 | all reviews |
| analyst_2_synthesis | ux-researcher | 3 | all reviews |
| analyst_3_synthesis | business-analyst | 3 | all reviews |
| final_recommendation | product-manager | 4 | all syntheses |
