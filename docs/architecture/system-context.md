# System Context

## System Purpose

Evidra.ai helps an authenticated individual professional turn confirmed career evidence into role-specific interview preparation through the Interview Sprint MBP flow.

## Primary Actor

The primary actor is an authenticated individual professional preparing for a specific interview or role. The MBP does not support organizations, teams, coaches, or enterprise administrators.

## Core System Diagram

```text
Browser
  → Django templates + HTMX
  → views/forms
  → services
  → ORM
  → PostgreSQL
```

## External Systems

- **Private object storage:** Stores uploaded resume files outside public access.
- **OpenAI API:** Produces structured outputs through the OpenAI Python SDK.
- **Razorpay:** Creates payment orders and sends verified payment webhooks.
- **One-page company URL fetch:** Fetches at most one user-supplied safe public company/product URL with safety limits.

## In-Repo Modules

- `accounts`: authentication and user ownership.
- `documents`: resume upload, paste, parsing, and active document state.
- `profiles`: career profile extraction and confirmation.
- `opportunities`: JD, role family, company context, and interview metadata.
- `evidence`: evidence cards, approval, provenance, and manual highlights.
- `stories`: reusable grounded stories.
- `matching`: story-to-opportunity matching and scoring.
- `previews`: free readiness preview.
- `payments`: Razorpay order and webhook handling.
- `prepkits`: paid preparation artifact.
- `practice`: text practice attempts and grounded feedback.
- `plans`: deterministic seven-day plan.
- `generations`: database-backed generation jobs.
- `common`: shared validators, constants, and workflow support.
- `ai`: AI client, schemas, prompts, services, and validators.

## Architecture Principles

- One Python modular monolith.
- Server-rendered UI with Django templates and HTMX.
- PostgreSQL as the system of record.
- Services own business rules.
- Workflow state is centralized and transactional.
- AI proposes content; application services validate and decide.
- External services are isolated behind interfaces and mocked in tests.
- User-owned data is never exposed cross-user.

## Request Flow

1. Browser submits a standard form or HTMX request.
2. View resolves authenticated user and owned resource.
3. Form validates user input.
4. Service applies business rules and ownership checks.
5. Service writes via ORM inside a transaction when state changes.
6. Response renders a Django template or partial.

## AI Operation Flow

1. Service loads approved and minimal inputs.
2. Service creates or reuses an idempotent `GenerationRun` when background work is needed.
3. `EvidraAIService` calls the OpenAI API with a fixed structured schema.
4. Pydantic validates output shape.
5. Grounding validators check source references and numeric claims.
6. Application service saves proposed output or failure.
7. Application service, not AI, decides state transitions.

## Payment Flow

1. User clicks the payment button from the preview.
2. Server creates a Razorpay order for the Sprint amount.
3. Sprint may move to `PAYMENT_PENDING`.
4. Browser redirect or client callback is informational only.
5. Razorpay webhook is verified server-side.
6. Signature, amount, order, event id, and Sprint mapping are validated.
7. Idempotent handler marks payment `PAID` and unlocks the Sprint entitlement.

## Background Generation Flow

1. Service creates a `GenerationRun` row for an operation and input revision.
2. Django management command claims pending jobs.
3. Command marks a job `RUNNING`.
4. Command runs the operation through services and `EvidraAIService`.
5. Command marks the job `SUCCEEDED` or `FAILED` with error metadata.
6. User can retry recoverable failures without losing prior work.

## Security Boundaries

- All reads and writes are user-scoped.
- Uploaded resumes are private.
- Resume binaries are never sent to AI.
- URL fetch blocks localhost, private IPs, file URLs, and internal hosts.
- Company fetch limits redirects, size, and duration.
- Payment access requires verified webhook, never browser redirect.
- Secrets are not committed.
- User-facing errors do not expose stack traces.

## Non-Goals

- Separate frontend/backend.
- Next.js.
- FastAPI.
- Redis/Celery.
- Microservices.
- Vector database or embeddings.
- Broad company web research.
- Production observability platform.
- Enterprise multi-tenancy.
