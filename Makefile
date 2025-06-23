.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS=":.*##"; OFS=""} {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

.PHONY: format
format: ## Format code and auto-fix format/lint issues
	uv run ruff format .
	uv run ruff check --fix-only --unsafe-fixes .

.PHONY: lint
lint: ## Check formatting & linting (no fixes)
	uv run ruff format --check .
	uv run ruff check .

.PHONY: types
types: ## Type-check using pyright in strict mode
	uv run pyright

.PHONY: contract
contract: ## Type contracts: cast/ignore only in engine.py
	@set -e; \
	if grep -R --include='*.py' --exclude-dir='__pycache__' --line-number -E '\bcast\(|# *type: *ignore' diplomacy_agents | grep -v 'diplomacy_agents/engine.py' ; then \
		echo '❌  Type-Safety Contract breached'; exit 1; \
	else \
		echo '✅  Type-Safety Contract upheld'; \
	fi

test: ## Run tests
	uv run pytest -vv

check-all: format lint types contract test ## Run all checks

check-ci: lint types contract test ## Run all checks

install: ## Create virtual-env and install project incl. dev deps using uv
	uv run pre-commit install --hook-type pre-commit --hook-type pre-push

run:  ## Run event-driven self-play match (seed 42)
	uv run -m diplomacy_agents.cli conductor
