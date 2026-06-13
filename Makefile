.PHONY: lint check test migrations-check

lint:
	python -m ruff check .

check:
	DJANGO_SETTINGS_MODULE=config.settings python -m django check

test:
	DJANGO_SETTINGS_MODULE=config.settings python -m pytest

migrations-check:
	DJANGO_SETTINGS_MODULE=config.settings python -m django makemigrations --check --dry-run
