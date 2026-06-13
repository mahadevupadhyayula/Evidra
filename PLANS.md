# Evidra MBP implementation plans

This repository follows the Python MBP source-of-truth documents in `docs/product/` and `docs/architecture/`.

## Stage discipline

- Implement one approved stage per branch.
- Do not begin a later stage until the current stage is reviewed and accepted.
- Do not implement deferred scope unless the relevant source-of-truth document is explicitly updated.
- Keep changes aligned with the Django modular monolith architecture.

## Approved implementation sequence

1. Foundation, authentication, resume and profile.
2. Opportunity context and approved evidence.
3. Reusable stories, contextual matching and free preview.
4. Razorpay payment and paid Prep Kit.
5. Text practice and seven-day plan.

## Planning rules

- Each implementation stage must cite the relevant product and architecture documents.
- Each stage must include ownership tests for user-owned data.
- External services must be mocked in automated tests.
- New migrations, dependencies and operational assumptions must be reported in the PR.
- Do not create production-scale architecture before MBP validation.
