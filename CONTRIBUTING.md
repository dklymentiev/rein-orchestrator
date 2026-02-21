# Contributing to Rein

Thanks for your interest in contributing to Rein. This guide covers what you need to get started.

## Development Setup

```bash
git clone https://github.com/rein-orchestrator/rein.git
cd rein
pip install -e ".[dev]"
```

This installs Rein in editable mode with all dev dependencies (pytest, anthropic, openai, websockets).

## Running Tests

```bash
pytest
```

Tests live in the `tests/` directory. Add tests for any new functionality.

## Code Style

- Python 3.10+ required (we use modern syntax including `match`, `|` unions, etc.)
- No strict linter enforced yet -- just keep it readable and consistent with existing code
- Use type hints where practical
- Docstrings on public classes and functions

## Adding a New Provider

Providers live in `rein/providers/`. To add one:

1. Create `rein/providers/your_provider.py`
2. Inherit from the `Provider` base class in `rein/providers/base.py`
3. Implement the `call(prompt: str, stage: str = "") -> Tuple[str, UsageStats]` method
4. Register your provider in `rein/providers/__init__.py`:
   - Import your class
   - Add an entry to the `PROVIDERS` dict
   - Add the class name to `__all__`

Example skeleton:

```python
from typing import Tuple
from .base import Provider, UsageStats

class YourProvider(Provider):
    def __init__(self, model: str = "", max_tokens: int = 4096,
                 temperature: float = 0.7, logger=None, **kwargs):
        super().__init__(model=model, max_tokens=max_tokens,
                         temperature=temperature, logger=logger, **kwargs)
        # Initialize your client here

    def call(self, prompt: str, stage: str = "") -> Tuple[str, UsageStats]:
        # Call your LLM API and return (response_text, usage_stats)
        result = "..."
        usage = UsageStats(
            input_tokens=0, output_tokens=0, cost=0.0,
            model=self.model, provider="your_provider", duration_ms=0
        )
        return result, usage
```

Then in `rein/providers/__init__.py`:

```python
from .your_provider import YourProvider

PROVIDERS = {
    ...
    "your_provider": YourProvider,
}
```

## Adding Examples

Examples live in `examples/` and follow a numbered naming convention (`01-hello-world`, `02-code-review`, etc.).

To add a new example:

1. Create a directory: `examples/NN-your-example/`
2. Include at minimum:
   - `agents/` directory with specialist `.md` files and/or team `.yaml` files
   - `workflow.yaml` defining the workflow
   - `README.md` explaining what the example does and how to run it
3. Keep examples self-contained -- they should work with just a provider API key set.

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b your-feature`)
3. Make your changes and add tests
4. Run `pytest` to make sure nothing is broken
5. Commit with a clear message describing what and why
6. Open a PR against `main`

Keep PRs focused on a single change. If you have multiple unrelated fixes, send separate PRs.

## Reporting Issues

Use GitHub Issues. Include:

- What you expected to happen
- What actually happened
- Rein version (`rein --version` or check `rein/__init__.py`)
- Python version
- Relevant config (workflow YAML, provider settings) with API keys redacted
