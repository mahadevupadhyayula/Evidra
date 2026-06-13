# Evidra MBP implementation plans

This repository follows the Python MBP source-of-truth documents in `docs/product/` and `docs/architecture/`.

## Stage discipline

- Implement one approved stage per branch.
- Do not begin a later stage until the current stage is reviewed and accepted.
- Do not implement deferred scope unless the relevant source-of-truth document is explicitly updated.
- Keep changes aligned with the Django modular monolith architecture.

## Approved implementation sequence

1. Iteration 1, Stage 1A: foundation, authentication, resume and profile planning.
2. Iteration 1, Stage 1B: foundation, authentication, resume and profile implementation.
3. Iteration 2: opportunity context and approved evidence.
4. Iteration 3: reusable stories, contextual matching and free preview.
5. Iteration 4: Razorpay payment and paid Prep Kit.
6. Iteration 5: text practice and seven-day plan.

## Planning rules

- Each implementation stage must cite the relevant product and architecture documents.
- Each stage must include ownership tests for user-owned data.
- External services must be mocked in automated tests.
- New migrations, dependencies and operational assumptions must be reported in the PR.
- Do not create production-scale architecture before MBP validation.
