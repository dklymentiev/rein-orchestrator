# Flow: Create Poem

**Team:** team-poetry
**Specialists:** poet-specialist, critic-specialist

## Description

Multi-round poetry creation workflow with iterative revision based on critical feedback.

## Blocks

### 1. Ideation (ideation.json)
Generate 5-10 poetry themes and ideas.

**Validation:** logic/validate-themes.py
- Checks that themes array exists
- Validates each theme has title and description

### 2. Draft (draft.json)
Write a poem based on one of the brainstormed themes.

**Enhancement:** logic/enhance-draft.py
- Adds metadata (line count, word count, char count)
- Formats output consistently

### 3. Critique (critique.json)
Critical analysis of the draft poem.

- Evaluates technical skill
- Assesses language and imagery
- Provides improvement suggestions
- Rates 1-10

### 4. Revision (final.json)
Revise the poem based on feedback.

**Validation:** logic/validate-revision.py
- Compares original vs revised
- Calculates size changes and metrics
- Adds comparison data

### 5. Final Critique (final_critique.json)
Final assessment of revised poem.

- Compares to original
- Provides final rating
- Success assessment

## Data Flow

```
ideation.json
    ↓
draft.json (enhanced with metadata)
    ↓
critique.json
    ↓
final.json (with comparison metrics)
    ↓
final_critique.json
```

## Logic Scripts

### validate-themes.py
- **Phase:** validate (after ideation block)
- **Input:** ideation.json
- **Checks:** themes array, required fields
- **Output:** validates or fails

### enhance-draft.py
- **Phase:** post (after draft block)
- **Input:** draft.json
- **Adds:** metadata (line count, word count)
- **Output:** enhanced draft.json

### validate-revision.py
- **Phase:** post (after revision block)
- **Input:** final.json
- **Compares:** original vs revised
- **Adds:** comparison metrics
- **Output:** enhanced final.json with metrics

## Example Run

```bash
cd /server/scripts/agent-pm2-dog
python3 dog.py agents/flows/create-poem/create-poem.yaml
```

## Results

All results saved as JSON files:
- `ideation.json` - Brainstormed themes
- `draft.json` - Initial poem with metadata
- `critique.json` - Critical feedback
- `final.json` - Revised poem with comparison
- `final_critique.json` - Final assessment

## Future Enhancements

1. Add custom validation rules per theme
2. Support multiple poems in parallel
3. Add sentiment analysis to critique
4. Generate summary report
5. Export to markdown or HTML
