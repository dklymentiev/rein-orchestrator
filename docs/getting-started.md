# Getting Started with Rein

Go from zero to a running multi-agent workflow in under 5 minutes.

Rein is a declarative YAML workflow orchestrator for multi-agent AI. You define
AI agents as Markdown files, group them into teams, and wire them together in
YAML workflows. No Python code required.

## Prerequisites

- **Python 3.10+** (check with `python3 --version`)
- **An LLM API key** -- one of:
  - [Anthropic](https://console.anthropic.com/) (Claude)
  - [OpenAI](https://platform.openai.com/) (GPT-4o)
  - [Ollama](https://ollama.com/) installed locally (free, no key needed)

## 1. Install Rein

Pick the provider you want to use:

```bash
# Anthropic Claude (recommended)
pip install rein-ai[anthropic]

# OpenAI GPT
pip install rein-ai[openai]

# All providers
pip install rein-ai[all]

# Ollama -- no extra SDK needed, just core
pip install rein-ai
```

Verify it installed:

```bash
rein --help
```

## 2. Set your API key

```bash
# Anthropic
export ANTHROPIC_API_KEY=sk-ant-...

# -- OR OpenAI --
export OPENAI_API_KEY=sk-...

# -- OR Ollama (no key needed, just make sure it's running) --
# ollama serve
```

> **Want to skip ahead?** Run the included example instead:
> ```bash
> cd examples/01-hello-world
> rein --agents-dir ./agents workflow.yaml --no-ui
> ```
> See [examples/01-hello-world/README.md](../examples/01-hello-world/README.md)
> for details. Otherwise, keep reading to build one from scratch.

## 3. Create your first workflow

Set up a project directory with the required structure:

```bash
mkdir -p my-first-workflow/agents/specialists
mkdir -p my-first-workflow/agents/teams
cd my-first-workflow
```

### 3a. Write a specialist

A specialist is a Markdown file that defines an AI agent's role and output format.

Create `agents/specialists/researcher.md`:

```markdown
# Researcher

You are a research analyst who investigates topics and produces structured findings.

## Goal

Given a topic, produce a concise research summary with key facts and sources.

## Output Format

Respond with valid JSON:

{"topic": "the topic studied", "summary": "2-3 sentence overview", "key_facts": ["fact 1", "fact 2", "fact 3"], "further_questions": ["question 1", "question 2"]}
```

### 3b. Write a team file

A team groups specialists and sets a shared collaboration tone.

Create `agents/teams/research-team.yaml`:

```yaml
name: research-team
description: "Solo researcher team"

specialists:
  - researcher

collaboration_tone: |
  Be thorough and factual. Always output valid JSON.
```

### 3c. Write the workflow

The workflow defines what to execute. Each unit of work is called a **block**.

Create `workflow.yaml` in the project root:

```yaml
schema_version: "2.6.0"
name: my-first-workflow
description: "Single-block research workflow"
team: research-team
max_parallel: 1

# Provider is auto-detected from your API key environment variable.
# To override, uncomment:
#   provider: anthropic
#   model: claude-sonnet-4-20250514

blocks:
  - name: research
    specialist: researcher
    prompt: |
      Research the following topic:

      "How does WebSocket differ from HTTP long-polling?"

      Follow your specialist instructions for output format.
    depends_on: []
```

Rein auto-detects your provider from the environment variable you set in step 2.
To use a specific provider/model, add `provider:` and `model:` to the YAML
(see the [README](../README.md#provider-configuration) for all options).

### 3d. Run it

```bash
rein --agents-dir ./agents workflow.yaml --no-ui
```

Rein will:

1. Load the team and specialist definitions
2. Execute the `research` block by sending the prompt (with the specialist's
   system instructions) to the configured LLM
3. Save the output to a run directory

### 3e. See the output

Results are written to `/tmp/rein-runs/run-YYYYMMDD-HHMMSS/`. Find the latest run:

```bash
ls -lt /tmp/rein-runs/ | head -5
```

Read the block output:

```bash
cat /tmp/rein-runs/run-*/research/outputs/result.json
```

You should see the JSON response from the researcher specialist.

## 4. Add a second block with dependencies

The real power of Rein is chaining blocks together. Let's add a **writer** that
takes the researcher's output and turns it into a blog post.

### 4a. Create the writer specialist

Create `agents/specialists/writer.md`:

```markdown
# Writer

You are a technical writer who turns research into clear, engaging articles.

## Goal

Given research findings as JSON, produce a well-structured article.

## Output Format

Respond with valid JSON:

{"title": "Article title", "article": "The full article text in Markdown format", "word_count": 350}
```

### 4b. Add the writer to the team

Update `agents/teams/research-team.yaml`:

```yaml
name: research-team
description: "Researcher + writer team"

specialists:
  - researcher
  - writer

collaboration_tone: |
  Be thorough and factual. Always output valid JSON.
```

### 4c. Add the second block to the workflow

Update `workflow.yaml` -- add the `write` block after the `research` block:

```yaml
schema_version: "2.6.0"
name: my-first-workflow
description: "Research then write workflow"
team: research-team
max_parallel: 1

blocks:
  - name: research
    specialist: researcher
    prompt: |
      Research the following topic:

      "How does WebSocket differ from HTTP long-polling?"

      Follow your specialist instructions for output format.
    depends_on: []

  - name: write
    specialist: writer
    depends_on: [research]
    prompt: |
      Write a short technical article based on this research:

      {{ research.json }}

      Follow your specialist instructions for output format.
```

Key things to notice:

- **`depends_on: [research]`** -- the `write` block waits for `research` to
  finish before it starts.
- **`{{ research.json }}`** -- this template variable is replaced at runtime
  with the full JSON output of the `research` block. This is how data flows
  between blocks.

### 4d. Run the two-block workflow

```bash
rein --agents-dir ./agents workflow.yaml --no-ui
```

Check both outputs:

```bash
cat /tmp/rein-runs/run-*/research/outputs/result.json
cat /tmp/rein-runs/run-*/write/outputs/result.json
```

The writer's output will be an article based on the researcher's findings.

## Your project structure

After these steps, your directory looks like this:

```
my-first-workflow/
  workflow.yaml
  agents/
    specialists/
      researcher.md
      writer.md
    teams/
      research-team.yaml
```

That is all you need. No Python files, no configuration boilerplate.

## Template variable reference

Use these in block prompts to pass data between blocks:

| Variable | Description |
|----------|-------------|
| `{{ blockname.json }}` | Full JSON output of a previous block |
| `{{ task.input.topic }}` | Input parameter (when using `--input '{"topic": "..."}'`) |
| `{{ task.input.* }}` | Any field from the JSON input |

## Troubleshooting

**`rein: command not found`**
Make sure the pip install directory is on your PATH. Try `python -m rein --help`
as a fallback, or re-install with `pip install --user rein-ai[anthropic]`.

**`Python 3.10+ required` / syntax errors on import**
Rein requires Python 3.10 or later. Check with `python3 --version`. If you have
multiple Python versions, use `python3.10 -m pip install rein-ai[anthropic]`.

**`API key not found` / authentication errors**
Verify your key is exported in the current shell:
```bash
echo $ANTHROPIC_API_KEY   # Should print sk-ant-...
```
If empty, re-export it. The variable must be set in the same terminal where you
run `rein`.

**No output / empty run directory**
Check `/tmp/rein-runs/` for the latest run. If missing, the workflow may have
failed -- re-run with `--no-ui` to see error messages in the terminal.

## Next steps

- **More examples**: See the [examples/](../examples/) directory for 5
  progressive tutorials covering parallel execution, deliberation patterns,
  conditional branching, and revision loops.
- **Full CLI reference**: The [README](../README.md) covers all command-line
  options, provider configuration, logic scripts, daemon mode, and the
  terminal UI.
- **Conditional branching**: Route execution based on block output using
  `next:` with `if:` / `else:` (see `examples/05-conditional/`).
- **Parallel execution**: Blocks with no dependencies run in parallel
  automatically. Control concurrency with `max_parallel`.
- **Logic scripts**: Add Python pre/post processing to any block with the
  `logic:` field (see README for details).
