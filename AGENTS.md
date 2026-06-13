# Evidra repository instructions

## Product authority

Read these before changing product behaviour:

- docs/product/evidra-python-mbp-blueprint.md
- docs/product/core-user-flow.md
- docs/product/implementation-rules.md
- docs/product/deferred-scope.md
- docs/architecture/state-machine.md
- docs/architecture/data-model.md
- docs/architecture/ai-runtime.md
- PLANS.md

The approved Python MBP blueprint determines scope.

Do not reintroduce the former ten-week production architecture.

## Architecture

- Use a Django modular monolith.
- Use Django templates and HTMX.
- Use PostgreSQL in deployed environments.
- Keep views thin.
- Put business rules in application services.
- Put deterministic state transitions in one workflow service.
- Use Pydantic for structured AI output validation.
- Mock external services in automated tests.
- Do not introduce Redis, Celery, microservices, pgvector, embeddings or agent frameworks.

## AI rules

- AI proposes structured output.
- AI never changes workflow state directly.
- AI never controls authentication, authorization, payment or deletion.
- AI must not invent achievements, employers or metrics.
- Unknown fields must remain null.
- Stories may use approved evidence only.
- Every generated story and recommendation must preserve source references.
- Retry structurally invalid AI output at most once.

## Data and ownership

- Every user-owned record must have direct or inherited user ownership.
- Every view and service must validate ownership.
- Never trust an object ID supplied by the browser without ownership filtering.
- Upstream edits mark dependent outputs stale.
- Do not automatically delete stale paid artifacts.

## Testing

Before reporting completion, run:

- make lint
- make check
- make test
- make migrations-check

Run stage-specific integration tests when applicable.

## Pull-request discipline

- Implement one approved stage per branch.
- Do not begin the next stage.
- Do not add deferred features.
- Report changed files, migrations, dependencies and tests.
- Do not commit secrets.

## Review guidelines

Treat these as release-blocking:

- Cross-user access.
- Unsupported AI-generated claims.
- Unapproved evidence entering stories.
- Payment access based only on a browser redirect.
- Missing webhook signature validation.
- AI-controlled workflow transitions.
- Destructive deletion of stale outputs.
- Live external calls in automated tests.
