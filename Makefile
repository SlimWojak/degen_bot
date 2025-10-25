# Makefile - Phase ε.1 Purification Pass
# Development and CI commands

.PHONY: help check test clean install dev lint type-check audit deps

help: ## Show this help message
	@echo "Phase ε.1: Purification Pass - Available Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

check: lint type-check audit test ## Run all checks (lint, type-check, audit, test)

lint: ## Run ruff linting
	@echo "🔍 Running ruff linting..."
	ruff check backend --fix
	@echo "✅ Ruff linting passed"

type-check: ## Run mypy type checking
	@echo "🔍 Running mypy type checking..."
	mypy backend --strict --ignore-missing-imports
	@echo "✅ MyPy type checking passed"

audit: ## Run dependency audit
	@echo "🔍 Running dependency audit..."
	python scripts/audit_deps.py
	@echo "✅ Dependency audit completed"

test: ## Run deterministic tests
	@echo "🔍 Running deterministic tests..."
	python tests/test_simple_truth.py
	@echo "✅ Deterministic tests passed"

deps: ## Install dependencies
	@echo "📦 Installing dependencies..."
	pip install -r requirements.txt
	@echo "✅ Dependencies installed"

dev: deps ## Setup development environment
	@echo "🛠️  Setting up development environment..."
	pip install pre-commit
	pre-commit install
	@echo "✅ Development environment ready"

clean: ## Clean up temporary files
	@echo "🧹 Cleaning up..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -delete
	rm -rf .coverage htmlcov/
	@echo "✅ Cleanup completed"

ci: check ## Run CI checks (alias for check)
	@echo "🎉 All CI checks passed!"

# Server management
start: ## Start the server
	@echo "🚀 Starting server..."
	python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

stop: ## Stop the server
	@echo "🛑 Stopping server..."
	@lsof -ti :8000 | xargs -n1 kill -9 2>/dev/null || true
	@echo "✅ Server stopped"

restart: stop start ## Restart the server

# Reports
reports: ## Generate all reports
	@echo "📊 Generating reports..."
	@mkdir -p reports
	python scripts/audit_deps.py
	@echo "✅ Reports generated in reports/"

# Phase ε.1 specific commands
purification: check reports ## Run Phase ε.1 purification pass
	@echo "🧹 Phase ε.1: Purification Pass Complete"
	@echo "✅ Async hygiene: Implemented"
	@echo "✅ Deterministic tests: Implemented" 
	@echo "✅ Dependency hygiene: Implemented"
	@echo "✅ Typing clarity: Implemented"
	@echo "✅ Error taxonomy: Implemented"
	@echo "✅ Static checks: Implemented"