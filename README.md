# Evidra.ai Python MBP

Evidra.ai is a Python-based, evidence-first Interview Sprint MBP.

The MBP value loop is:

Resume → Profile → Opportunity Context → Approved Evidence → Reusable Stories → Contextual Matching → Free Preview → Payment → Prep Kit → Text Practice → Seven-Day Plan

## Source of truth

Read these documents before implementation:

- `docs/product/evidra-python-mbp-blueprint.md`
- `docs/product/core-user-flow.md`
- `docs/product/implementation-rules.md`
- `docs/product/deferred-scope.md`
- `docs/architecture/system-context.md`
- `docs/architecture/state-machine.md`
- `docs/architecture/ai-runtime.md`
- `docs/architecture/data-model.md`
- `AGENTS.md`
- `PLANS.md`

## Approved architecture

- Django modular monolith.
- Django templates and HTMX.
- PostgreSQL.
- Private resume storage.
- OpenAI Python SDK with Pydantic structured outputs.
- Database-backed `GenerationRun` worker using a Django management command.
- Razorpay for the first MBP payment provider.

## Local setup

1. Create and activate a Python 3.12+ virtual environment.
2. Install dependencies with `python -m pip install -r requirements-dev.txt`.
3. Copy `.env.example` to `.env` and adjust local settings as needed.
4. Start PostgreSQL with `docker compose up -d postgres` when using the sample `DATABASE_URL`.
5. Run migrations with `DJANGO_SETTINGS_MODULE=config.settings python manage.py migrate`.
6. Start the app with `DJANGO_SETTINGS_MODULE=config.settings python manage.py runserver`.

If `DATABASE_URL` is unset, local commands default to SQLite for lightweight development and tests. Deployed environments should configure PostgreSQL.

## Quality checks

Run these before reporting completion:

- `make lint`
- `make check`
- `make test`
- `make migrations-check`

## Explicit non-goals for the MBP

Do not introduce Next.js, FastAPI, Redis, Celery, microservices, pgvector, embeddings, multi-agent orchestration, subscriptions, audio/video practice, mobile apps, browser extensions or production-scale observability.

## Repository status

Stage 1A has introduced the Django foundation, email/password accounts, session handling, workspace page, and deterministic Interview Sprint workflow foundation.
