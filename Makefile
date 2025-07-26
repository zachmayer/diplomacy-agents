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
types: ## Type-check using pyright
	uv run pyright

.PHONY: no-type-ignore
no-type-ignore: ## Type contracts: no type ignore allowed
	@set -e; \
	if grep -R --include='*.py' --exclude-dir='__pycache__' --line-number -E '# *type: *ignore' diplomacy_agents ; then \
		echo '❌  Type-Safety Contract breached (no type: ignore allowed)'; exit 1; \
	else \
		echo '✅  Type-Safety Contract upheld'; \
	fi

.PHONY: no-noqa
no-noqa: ## Type contracts: no noqa allowed
	@set -e; \
	if grep -R --include='*.py' --exclude-dir='__pycache__' --line-number -E '# *noqa: *' diplomacy_agents ; then \
		echo '❌  Noqa Contract breached (no noqa allowed)'; exit 1; \
	else \
		echo '✅  Noqa Contract upheld'; \
	fi

.PHONY: no-cast
no-cast: ## Type contracts: no cast allowed
	@set -e; \
	if grep -R --include='*.py' --exclude-dir='__pycache__' --line-number -E '.cast\(' diplomacy_agents ; then \
		echo '❌  Cast Contract breached (no cast allowed)'; exit 1; \
	else \
		echo '✅  No Cast Contract upheld'; \
	fi

.PHONY: contract
contract: no-type-ignore no-noqa no-cast ## Type contracts: no type ignore or cast allowed

.PHONY: test-unit
test-unit: ## Run fast unit tests (everything except smoke)
	uv run pytest -vv -k "not smoke"

.PHONY: test-smoke
test-smoke: ## Run slower conductor smoke test
	uv run pytest -vv -k "smoke"

.PHONY: test
test: test-unit test-smoke ## Run all tests (unit then smoke)

.PHONY: coverage
coverage: ## Run tests with coverage reporting
	uv run coverage run -m pytest && uv run coverage report --fail-under 97

.PHONY: all
all: format lint types contract test coverage ## Run all checks

.PHONY: check-ci
check-ci: lint types contract test-unit ## Checks for CI (unit tests only)

.PHONY: install
install: ## Create virtual-env and install project incl. dev deps using uv
	uv run pre-commit install --hook-type pre-commit --hook-type pre-push

.PHONY: run
run: ## Run one experiment with ExperimentRunner (single game)
	uv run -m diplomacy_agents.cli experiments --runs 1

.PHONY: run-ten
run-ten: ## Run ten experiments with ExperimentRunner (single game)
	uv run -m diplomacy_agents.cli experiments --runs 5

.PHONY: clean
clean: ## Clean up all generated files
	rm -rf .venv
	rm -rf .DS_Store
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf .coverage
	rm -rf .coverage.*
	rm -rf .coverage.xml
	rm -rf .coverage.json
	rm -rf .coverage.html
	rm -rf .coverage.lcov
	rm -rf .coverage.xml
	rm -rf htmlcov
	rm -rf uv.lock
	rm -rf artifacts/
	rm -rf __pycache__/
	rm -rf tests/__pycache__/
	rm -rf diplomacy_agents/__pycache__/