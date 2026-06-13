# Evidra MBP implementation plans

This repository follows the Python MBP source-of-truth documents in `docs/product/` and `docs/architecture/`.

## Stage discipline

- Implement one approved stage per branch.
- Do not begin a later stage until the current stage is reviewed and accepted.
- Do not implement deferred scope unless the relevant source-of-truth document is explicitly updated.
- Keep changes aligned with the Django modular monolith architecture.

## Approved implementation sequence

### Iteration 1: Foundation, accounts, resume and profile

1. Stage 1A: Django foundation, accounts and Sprint workflow.
2. Stage 1B: Resume intake, parsing and confirmation.
3. Stage 1C: AI profile extraction and confirmation.

### Iteration 2: Opportunity context and approved evidence

1. Stage 2A: Opportunity form, role packs and JD analysis.
2. Stage 2B: Limited company-context retrieval.
3. Stage 2C: Highlights, evidence extraction and approval.

### Iteration 3: Stories, matching and preview

1. Stage 3A: Reusable stories and story scoring.
2. Stage 3B: Contextual matching.
3. Stage 3C: Free readiness preview.

### Iteration 4: Payment, generation worker and Prep Kit

1. Stage 4A: Razorpay payment.
2. Stage 4B: Database-backed generation worker.
3. Stage 4C: Paid Prep Kit.

### Iteration 5: Practice, plan and validation

1. Stage 5A: Text practice.
2. Stage 5B: Rule-based seven-day plan.
3. Stage 5C: End-to-end MBP validation.

## Planning rules

- Each implementation stage must cite the relevant product and architecture documents.
- Each stage must include ownership tests for user-owned data.
- External services must be mocked in automated tests.
- New migrations, dependencies and operational assumptions must be reported in the PR.
- Do not create production-scale architecture before MBP validation.
