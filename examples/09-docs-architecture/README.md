# Example 09: Documentation & Architecture Review

Architecture deliberation with Software Architect, API Designer, and Product Manager perspectives across 4 phases.

## What You'll Learn

- **Multi-perspective architecture review**: Technical, API, and product viewpoints
- **4-phase deliberation**: Same thorough pattern as Example 06, different domain
- **Cross-disciplinary feedback**: Architect considers UX, PM considers technical constraints
- **Architecture Decision Records**: Structured output for documenting decisions

## How It Works

```
Phase 1: Independent Analysis (parallel)
  architect_initial        -- system design, data models, technical risks
  api_designer_initial     -- API consolidation, DX, versioning
  product_manager_initial  -- user experience, use cases, adoption

Phase 2: Cross-Review (parallel)
  architect_review        -- technical constraints others missed
  api_designer_review     -- API/DX concerns others missed
  product_manager_review  -- user/business concerns others missed

Phase 3: Synthesis (parallel)
  architect_synthesis
  api_designer_synthesis
  product_manager_synthesis

Phase 4: Final Consolidation
  final_recommendation    -- unified architecture decision
```

## Structure

```
09-docs-architecture/
  workflow.yaml
  agents/
    specialists/
      architect-specialist.md       -- System design and scalability
      api-designer-specialist.md    -- REST API design and DX
      product-manager-specialist.md -- User value and business outcomes
    teams/
      team-deliberation.yaml
```

## Run

```bash
cd examples/09-docs-architecture
rein --agents-dir ./agents workflow.yaml --no-ui \
  --input '{"topic": "Should we merge our 3 separate document APIs into a unified platform?"}'
```

## Key Pattern: Architecture Deliberation

Architecture decisions benefit from multiple perspectives:

- **Architect** sees system complexity, data models, migration risks
- **API Designer** sees developer experience, endpoint design, versioning
- **Product Manager** sees user mental models, adoption risks, business value

The 4-phase structure ensures each perspective is heard, challenged, and integrated.

## 10 Blocks, 3 Specialists

| Block | Specialist | Phase | Depends On |
|-------|-----------|-------|------------|
| architect_initial | architect-specialist | 1 | -- |
| api_designer_initial | api-designer-specialist | 1 | -- |
| product_manager_initial | product-manager-specialist | 1 | -- |
| architect_review | architect-specialist | 2 | api_designer, pm |
| api_designer_review | api-designer-specialist | 2 | architect, pm |
| product_manager_review | product-manager-specialist | 2 | architect, api |
| architect_synthesis | architect-specialist | 3 | all reviews |
| api_designer_synthesis | api-designer-specialist | 3 | all reviews |
| product_manager_synthesis | product-manager-specialist | 3 | all reviews |
| final_recommendation | architect-specialist | 4 | all syntheses |
