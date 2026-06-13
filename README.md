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

## Explicit non-goals for the MBP

Do not introduce Next.js, FastAPI, Redis, Celery, microservices, pgvector, embeddings, multi-agent orchestration, subscriptions, audio/video practice, mobile apps, browser extensions or production-scale observability.

## Repository status

This repository currently contains source-of-truth documentation and repository control files only. It is not yet a Django project.
