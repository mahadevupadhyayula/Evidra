.PHONY: lint check test migrations-check

lint:
	python -m ruff check .

check:
	python -m django check

test:
	python -m pytest

migrations-check:
	python -m django makemigrations --check --dry-run
