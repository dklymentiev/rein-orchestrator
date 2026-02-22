# Example 10: Creative Writing with Logic Scripts

Iterative poetry creation with validation and post-processing scripts -- demonstrates Rein's logic pipeline.

## What You'll Learn

- **Logic scripts**: Python scripts that validate and enrich LLM output
- **`validate:` hook**: Runs after LLM output, fails the block if output is invalid
- **`post:` hook**: Runs after LLM output, enriches data with computed metadata
- **Sequential pipeline**: Each block depends on the previous one
- **Creative workflow**: Ideation -> draft -> critique -> revision -> final assessment

## How It Works

```
ideation ──[validate: validate-themes.py]──> draft ──[post: enhance-draft.py]──>
critique ──> revision ──[post: validate-revision.py]──> final_critique
```

Each logic script does pure Python work (no LLM calls):
- `validate-themes.py` -- checks JSON structure has valid themes array
- `enhance-draft.py` -- adds word count, line count, character count metadata
- `validate-revision.py` -- compares original vs revised, adds size change metrics

## Structure

```
10-creative-writing/
  workflow.yaml
  logic/
    validate-themes.py    -- Validates ideation output structure
    enhance-draft.py      -- Adds metadata to draft
    validate-revision.py  -- Compares original vs revised poem
  agents/
    specialists/
      poet-specialist.md    -- Creates and revises poetry
      critic-specialist.md  -- Evaluates and critiques poetry
    teams/
      team-poetry.yaml
```

## Run

```bash
cd examples/10-creative-writing
rein --agents-dir ./agents workflow.yaml --no-ui

# Or with a specific theme:
rein --agents-dir ./agents workflow.yaml --no-ui \
  --input '{"topic": "the passage of time"}'
```

## Key Pattern: Logic Scripts

Logic scripts are the RIGHT way to add non-LLM processing to Rein workflows:

```yaml
# Validate output structure (fails block if invalid)
logic:
  validate: logic/validate-themes.py

# Enrich output with computed data
logic:
  post: logic/enhance-draft.py
```

**When to use logic scripts:**
- JSON structure validation
- Adding computed metadata (counts, metrics, timestamps)
- Data transformation between blocks
- Quality gates (exit code 1 = block fails)

**When NOT to use logic scripts:**
- LLM calls (let Rein handle those natively)
- Template substitution (Rein does `{{ }}` natively)

## 5 Blocks, 2 Specialists

| Block | Specialist | Logic | Depends On |
|-------|-----------|-------|------------|
| ideation | poet-specialist | validate: validate-themes.py | -- |
| draft | poet-specialist | post: enhance-draft.py | ideation |
| critique | critic-specialist | -- | draft |
| revision | poet-specialist | post: validate-revision.py | critique |
| final_critique | critic-specialist | -- | revision |
