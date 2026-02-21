# Example 1: Hello World

The simplest possible Rein workflow -- one specialist, one task.

## What it does

A single "summarizer" specialist reads a text and produces a structured JSON summary.

## Structure

```
01-hello-world/
  workflow.yaml              -- workflow definition
  agents/
    specialists/
      summarizer.md          -- specialist prompt
    teams/
      team-hello.yaml        -- team definition
```

## Run it

```bash
# Set your API key
export ANTHROPIC_API_KEY=sk-...

# Run the workflow
rein --agents-dir ./agents workflow.yaml --no-ui

# Or with OpenAI
export OPENAI_API_KEY=sk-...
# Edit workflow.yaml: provider: openai, model: gpt-4o
rein --agents-dir ./agents workflow.yaml --no-ui
```

## Output

Results are saved to a task directory:

```
/tmp/rein-runs/run-YYYYMMDD-HHMMSS/
  summarize/
    outputs/
      result.json    -- the specialist's response
```

## Key concepts

- **Specialist** (`summarizer.md`): Markdown file defining the AI agent's role, output format, and guidelines
- **Team** (`team-hello.yaml`): Groups specialists and sets a shared collaboration tone
- **Workflow** (`workflow.yaml`): Defines what to execute, in what order
- **Block**: A single unit of work in a workflow (here: `summarize`)
