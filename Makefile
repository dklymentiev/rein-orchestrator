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

build:  ## Build distribution packages
	python -m build

clean:  ## Remove build artifacts
	rm -rf build/ dist/ *.egg-info htmlcov/ .mypy_cache/ .pytest_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

.PHONY: help install-dev test lint format format-check typecheck coverage build clean
