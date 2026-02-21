# Example 2: Code Review

Two specialists working sequentially -- a reviewer finds issues, then an improver fixes them.

## What it does

1. **code-reviewer** analyzes a Python function for bugs, security issues, and style
2. **code-improver** reads the review feedback and produces corrected code

The second block depends on the first (`depends_on: [review]`), so they run in sequence.

## Structure

```
02-code-review/
  workflow.yaml
  agents/
    specialists/
      code-reviewer.md       -- finds issues
      code-improver.md       -- fixes issues
    teams/
      team-code-review.yaml
```

## Run it

```bash
export ANTHROPIC_API_KEY=sk-...
rein --agents-dir ./agents workflow.yaml --no-ui
```

## Key concepts

- **Sequential execution**: `depends_on: [review]` makes the improve block wait for review to finish
- **Data flow**: `{{ review.json }}` injects the reviewer's output into the improver's prompt
- **Multiple specialists**: Each block uses a different specialist with different expertise
