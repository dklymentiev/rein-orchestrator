# Example 07: Brainstorm

Divergent thinking with 3 parallel ideation specialists, cross-pollination, and synthesis.

## What You'll Learn

- **Divergent-convergent pattern**: Generate many ideas first, then refine
- **Cross-pollination**: Specialists build on each other's ideas
- **Specialized ideation roles**: Different thinking styles produce different ideas
- **Synthesis**: Combining raw ideas into actionable concepts

## How It Works

```
Phase 1: Divergent Generation (parallel)
  divergent_ideas   -- 20+ wild ideas, no filtering
  industry_ideas    -- 15+ industry-grounded ideas
  contrarian_ideas  -- 10+ assumption-breaking ideas

Phase 2: Cross-Pollination (parallel)
  divergent_builds  -- "Yes, and..." on others' ideas
  industry_builds   -- industry lens on all ideas
  contrarian_builds -- challenge everything, find gaps

Phase 3: Synthesis
  final_synthesis   -- top 15 concepts, quick wins, moonshots
```

## Structure

```
07-brainstorm/
  workflow.yaml
  agents/
    specialists/
      divergent-thinker.md   -- Quantity over quality, wild ideas
      industry-expert.md     -- Domain knowledge, best practices
      contrarian-thinker.md  -- Challenge assumptions, flip constraints
      synthesizer.md         -- Combine, prioritize, package
    teams/
      team-brainstorm.yaml
```

## Run

```bash
cd examples/07-brainstorm
rein --agents-dir ./agents workflow.yaml --no-ui \
  --input '{"topic": "How to improve developer onboarding for our open-source project?"}'
```

## Key Pattern: Divergent-Convergent

This pattern maximizes creative output:

1. **Diverge** -- Multiple specialists generate ideas independently (no groupthink)
2. **Cross-pollinate** -- Each specialist reads others' ideas and builds on them
3. **Converge** -- A synthesizer combines everything into prioritized concepts

The result is 60+ raw ideas distilled into 15 actionable concepts with effort estimates and priorities.

## 7 Blocks, 4 Specialists

| Block | Specialist | Phase | Depends On |
|-------|-----------|-------|------------|
| divergent_ideas | divergent-thinker | 1 | -- |
| industry_ideas | industry-expert | 1 | -- |
| contrarian_ideas | contrarian-thinker | 1 | -- |
| divergent_builds | divergent-thinker | 2 | all phase 1 |
| industry_builds | industry-expert | 2 | all phase 1 |
| contrarian_builds | contrarian-thinker | 2 | all phase 1 |
| final_synthesis | synthesizer | 3 | all phase 2 |
