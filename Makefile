.PHONY: test lint format coverage hooks clean

# Testing
test:
	uv run pytest libs/ apps/ -v --tb=short

coverage:
	uv run pytest libs/ apps/ -v --tb=short --cov --cov-report=term-missing

# Linting
lint:
	uv run ruff check .

format:
	uv run ruff format .

# Setup
hooks:
	git config core.hooksPath .githooks
	chmod +x .githooks/*
	@echo "Git hooks configured."

# Cleanup
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov/
	@echo "Cleaned."
