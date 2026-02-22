.DEFAULT_GOAL := help

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install-dev:  ## Install in editable mode with dev deps
	pip install -e ".[dev]"

test:  ## Run tests with coverage
	pytest --cov=rein --cov-report=term-missing --tb=short -q

lint:  ## Run ruff linter
	ruff check rein/ models/

format:  ## Run ruff formatter
	ruff format rein/ models/ tests/

format-check:  ## Check formatting without changes
	ruff format --check rein/ models/ tests/

typecheck:  ## Run mypy type checker
	mypy rein/

coverage:  ## Run tests with HTML coverage report
	pytest --cov=rein --cov-report=html --cov-report=term-missing --tb=short -q
	@echo "Report: htmlcov/index.html"

check-release:  ## Pre-release checks (English-only, no emoji, no non-ASCII)
	@echo "Checking for non-ASCII characters in source code..."
	@FAILS=0; \
	for f in $$(find rein/ models/ schemas/ -name '*.py' -o -name '*.json' | sort); do \
		if LC_ALL=C grep -Pn '[^\x00-\x7E]' "$$f" 2>/dev/null; then \
			echo "  ^^^ $$f"; FAILS=1; \
		fi; \
	done; \
	echo "Checking documentation..."; \
	for f in $$(find . -maxdepth 1 -name '*.md' | sort) docs/*.md examples/*/README.md; do \
		[ -f "$$f" ] || continue; \
		if LC_ALL=C grep -Pn '[^\x00-\x7E]' "$$f" 2>/dev/null; then \
			echo "  ^^^ $$f"; FAILS=1; \
		fi; \
	done; \
	echo "Checking workflow/team YAML files..."; \
	for f in $$(find examples/ -name '*.yaml' -o -name '*.yml' | sort); do \
		if LC_ALL=C grep -Pn '[^\x00-\x7E]' "$$f" 2>/dev/null; then \
			echo "  ^^^ $$f"; FAILS=1; \
		fi; \
	done; \
	echo "Checking specialist definitions..."; \
	for f in $$(find examples/ -name '*.md' ! -name 'README.md' | sort); do \
		if LC_ALL=C grep -Pn '[^\x00-\x7E]' "$$f" 2>/dev/null; then \
			echo "  ^^^ $$f"; FAILS=1; \
		fi; \
	done; \
	if [ $$FAILS -eq 1 ]; then \
		echo ""; \
		echo "[FAIL] Non-ASCII characters found. Only English text allowed in release."; \
		exit 1; \
	else \
		echo "[OK] All files are ASCII-only (English)."; \
	fi

build:  ## Build distribution packages
	python -m build

clean:  ## Remove build artifacts
	rm -rf build/ dist/ *.egg-info htmlcov/ .mypy_cache/ .pytest_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

.PHONY: help install-dev test lint format format-check typecheck coverage build clean check-release
