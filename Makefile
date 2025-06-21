.PHONY: help install format lint types
.DEFAULT_GOAL := help

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS=":.*##"; OFS=""} {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

all: install format lint types ## Run all checks

format: ## Format code and auto-fix simple issues
	uv run ruff format .
	uv run ruff check --fix-only .

lint: ## Check formatting & linting (no fixes)
	uv run ruff format --check .
	uv run ruff check .

types: ## Type-check using pyright in strict mode
	uv run pyright

install: ## Create virtual-env and install project incl. dev deps using uv
	uv run pre-commit install --hook-type pre-commit --hook-type pre-push

run: ## Run the main.py file
	uv run main.py